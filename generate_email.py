#!/usr/bin/env python
# Author: Justin Mammarella
# Date:   22/02/2016
# Description: Email generator for user notification.
#             Based on nectar-tools/announce

import os
import sys
import re
import argparse
import smtplib
import logging
import datetime
import os_client_config
from collections import OrderedDict

from keystoneauth1 import identity as keystone_identity
from keystoneauth1 import session as keystone_session
from keystoneclient import client as keystone_client
from keystoneclient.exceptions import NotFound
from novaclient import client as nova_client

from jinja2 import Environment, FileSystemLoader


email_pattern = re.compile('([\w\-\.\']+@(\w[\w\-]+\.)+[\w\-]+)')

OUTPUT_FORMAT = '{: <40} {: <1} {: <40} {: <1} {: <40} {: <1}'

def get_session(url=None, username=None, password=None,
                tenant=None, version=3):
    url = os.environ.get('OS_AUTH_URL', url)
    username = os.environ.get('OS_USERNAME', username)
    user_domain_name = 'Default'
    password = os.environ.get('OS_PASSWORD', password)
    tenant = os.environ.get('OS_TENANT_NAME', tenant)
    project_domain_name = 'Default'
    assert url and username and password and tenant
    auth = keystone_identity.Password(username=username,
                                      password=password,
                                      tenant_name=tenant,
                                      auth_url=url,
                                      user_domain_name=user_domain_name,
                                      project_domain_name=project_domain_name)
    return keystone_session.Session(auth=auth)


def get_users(keystone, project):
    assignments = keystone.role_assignments.list(project=project)
    user_ids = set()
    for assignment in assignments:
        if hasattr(assignment, 'user'):
            user_ids.add(assignment.user['id'])
    data = []
    for user_id in user_ids:
        user = get_user(keystone, user_id)
        data.append(user)
    return data


def get_user(keystone, name_or_id):
    try:
        user = keystone.users.get(name_or_id)
    except NotFound:
        user = keystone.users.find(name=name_or_id)
    return user


def display_break(c):
    width = len(OUTPUT_FORMAT.format("", "", "", "", "", ""))
    output_text(c * width)


def display_header(h1, h2):
    display_break('=')
    display_column(h1, h2)
    display_break('=')


def display_column(c1=" ", c2=" ", c3=" ", c4=" "):
    output_text(OUTPUT_FORMAT.format(c1,  "|",  c2, "|", c3, "|", c4))


def output_text(output, print_me=0):
    global log_file
    if print_me == 1:
        print output
    log_file.write(output + "\n")


def collect_args():

    parser = argparse.ArgumentParser(
        description='Notifies users of an upcoming outage')

    parser.add_argument('-z', '--target-zone',
                        default=None,
                        help='Availability zone affected by outage')
    parser.add_argument('-n', '--node',
                        default=None,
                        help='Only target instances from a single Host/Node')
    parser.add_argument('--status',
                        default=None,
                        help='Only consider instances with status')
    parser.add_argument('-tr', '--test_recipient',
                        default=None,
                        help='Only generate a notification for this \
                              email address')
    parser.add_argument('-p', '--smtp_server',
                        default='127.0.0.1',
                        help='SMTP server to use, defaults to localhost')
    parser.add_argument('-st', '--start_time', action='store',
                        type=get_datetime,
                        help='Outage start time (e.g. \'09:00 25-06-2015\')',
                        required=True)
    parser.add_argument('-d', '--duration', action='store', type=int,
                        help='Duration of outage in hours', required=True)
    parser.add_argument('-tz', '--timezone', action='store',
                        help='Timezone (e.g. AEDT)', required=True)
    parser.add_argument('-t', '--template', action='store',
                        help='Name of template to use. Templates to be\
                              stored in ./template/',
                        required=True)

    return parser


def get_datetime(dt_string):
    return datetime.datetime.strptime(dt_string, '%H:%M %d-%m-%Y')


def create_notification(user, start_ts, end_ts, tz, zone, node,
                        test_recipient, work_dir, template):
    instances = user['instances']
    email = user['email']
    name = user['name']
    enabled = user['enabled']
    subject = 'NeCTAR Research Cloud outage'

    affected_instances = 0
    for project, servers in instances.iteritems():
        for server in servers:
            affected_instances += 1

    affected = bool(affected_instances)
    if affected:
        subject += ' affecting your instances'

    if not enabled:
        return False
    if email is None:
            # print 'User %s: no email address' % name
        return False
    if email_pattern.match(email) is None:
            # print 'User %s: invalid email address => %s' % (name, email)
        return False
# print work_dir + '/' + email

    msg = 'User %s: sending email to %s => %s instances affected' % \
          (name, email, affected_instances)

    if affected_instances > 0:
        render_templates(subject, instances, start_ts, end_ts, tz,
                         zone, affected, node, work_dir + '/' + email,
                         template)
        return True

    return False


def render_templates(subject, instances, start_ts, end_ts, tz, zone,
                     affected, node, filename, template):

    duration = end_ts - start_ts
    days = duration.days
    hours = duration.seconds//3600

    env = Environment(loader=FileSystemLoader('templates'))
    text = env.get_template(template)
    text = text.render(
                    {'instances': instances,
                     'zone': zone,
                     'start_ts': start_ts,
                     'end_ts': end_ts,
                     'days': days,
                     'hours': hours,
                     'tz': tz,
                     'node': node,
                     'affected': affected})
    with open(filename, "wb") as fh:
        fh.write("Subject: " + subject + '\n')
        fh.write(text)

    return text


def send_email(recipient, subject, text, html):
    return 0

def get_instances(client, zone=None, inst_status=None, node=None):
    marker = None
    # Collect instances for a single Node
    if node:
        response = client.servers.list(search_opts={'all_tenants': 1,
                                                    'host': node})
        for server in response:
            yield server
    # Collect instances for entire availability zone
    # marker - "begin returning servers that appear later in the server
    # list than that represented by this server id
    # There must be a return limit on the number of servers, so we need
    # to keep scanning until the response is null, shifting the marker
    # each time.

    else:
        while True:
            opts = {'all_tenants': True}
            if inst_status is not None:
                opts['status'] = inst_status
            if marker:
                opts['marker'] = marker
            response = client.servers.list(search_opts=opts)
            if not response:
                break
            for instance in response:
                marker = instance.id
                instance_az = (
                    instance._info.get('OS-EXT-AZ:availability_zone') or '')

                if zone and not instance_az.lower() == zone.lower():
                    continue
                yield instance


def populate_tenant(keystone, tenant, tenant_data):
    users = get_users(keystone, tenant)
    name = tenant.name
    if tenant.id not in tenant_data:
        tenant_data[tenant.id] = {'users': users, 'instances': []}
    else:
        tenant_data[tenant.id]['users'] = users
    tenant_data[tenant.id]['name'] = name


def populate_tenant_users(tenant, data, target_zone, user_data):

    tenant_name = data['name']

    users = data['users']

    try:
        instances = data['instances']
    except KeyError:
        instances = []

    instances_in_az = []
    for instance in instances:
        zone = getattr(instance, 'OS-EXT-AZ:availability_zone')
        if zone == target_zone or target_zone is None:
            instances_in_az.append(instance)

    affected_instances = len(instances_in_az)
    output_text(" ")
    display_break('=')
    display_column(tenant_name, tenant)
    display_break('=')
    output_text("Affected instances: ")
    output_text(" ")

    for instance in instances_in_az:
        zone = getattr(instance, 'OS-EXT-AZ:availability_zone')
        node = getattr(instance, 'OS-EXT-SRV-ATTR:host')
        display_column(instance.name[:40], instance.id, node, zone)
    display_break(' ')

    output_text("Users: ")
    output_text(" ")
    for user in users:
        user = populate_user(user, user_data)
        display_column(str(user['email'])[:40])
        for instance in instances_in_az:
            if tenant_name not in user['instances']:
                    user['instances'][tenant_name] = []
            user['instances'][tenant_name].append(instance)

    return affected_instances


def populate_user(user, user_data):
    if user.id not in user_data:
        user_data[user.id] = {'instances': {},
                              'email': user._info.get('email', None),
                              'enabled': user.enabled,
                              'name': user.name}
    return user_data[user.id]

class user_obj():
   def __init__(self,user):
        self.id = user.id
        self.instances = []
        self.email = user._info.get('email',None)
        self.enabled = user.enabled
        self.name = user.name

class tenant_obj():
   def __init__(self):
        self.id = ""
        self.name = ""
        self.instances = []
        self.users = []
        self.floating_ips = []

def main():

    args = collect_args().parse_args()

    sess = get_session(url=None, username=None, password=None,
                       tenant=None, version=3)
     
    kc = keystone_client.Client(3, session=sess)
    nc = nova_client.Client(2, session = sess)

    
   
    zone = args.target_zone
    smtp_server = args.smtp_server
    inst_status = args.status
    test_recipient = args.test_recipient

    start_ts = args.start_time
    end_ts = start_ts + datetime.timedelta(hours=args.duration)

    template = args.template
    node = args.node

    if not os.path.exists("./templates/" + template):
        print "Template could not be found."
        sys.exit(1)

    # Create Outbox Directory and Work Directory
    work_dir = './outbox/' + datetime.datetime.now().strftime("%y-%m-%d_" +
                                                              "%H:%M:%S")
    print "Creating Outbox: " + work_dir
    os.makedirs(work_dir)

    global log_file
    log_file = open(work_dir + '/' + "notify.log", "w")
    log_file.write(datetime.datetime.now().strftime("%y-%m-%d_%H:%M:%S"))

    print "Collecting instances"

    # List instances affected by outage
    affected_instances = list(get_instances(nc, zone, inst_status, node))
    
    # List tenants associated with affected instances
    affected_tenants = set([instance.tenant_id for instance in affected_instances])

    print "Collecting projects"
    # Tenant data
    tenants = kc.projects.list();

    #For each affected tenant get the users in the tenant
    tenant_list = [] 
    print "Get users per project"

    for t in affected_tenants:
                
        new_tenant = tenant_obj()
        for p in tenants:
            if t == p.id:
                new_tenant.id = p.id
                new_tenant.name = p.name
                new_tenant.users = get_users(kc, t)
        tenant_list.append(new_tenant)
    
    
    #Add affected instance objects to tenants.

    for instance in affected_instances:
        for t in tenant_list:
            if t.id == instance.tenant_id:
                t.instances.append(instance)


    print "Gathering tenant information."
    proceed = False
   
    user_data = {}
   
    for t in tenant_list:
        for user in t.users:
            populate_user(user, user_data)
            for instance in t.instances:
                cur_user = user_data[user.id]
                if t.name not in cur_user['instances']:
                    cur_user['instances'][t.name] = []
                cur_user['instances'][t.name].append(instance)

    for user in kc.users.list():
        populate_user(user, user_data)
    
    print "Generating notification emails."
    count = 0
    proceed = False
    

    for uid, user in user_data.iteritems():
        if test_recipient:
            # Generate emails for only one email address
            if user['email'] == test_recipient:
                if create_notification( user, start_ts, end_ts,
                                       args.timezone, zone, args.node,
                                       test_recipient, work_dir,
                                       template):
                    count += 1
        else:
            if create_notification( user, start_ts, end_ts, args.timezone,
                                   zone, args.node, test_recipient, work_dir,
                                   template):
                    count += 1

    print '\nTotal instances affected in %s zone: %s' % (zone, len(affected_instances))
    print '\nGenerated %s email notifications.' % count
    log_file.close()

    print "\nEmails to be sent stored in: " + work_dir

    print "\nLog stored in: " + work_dir + '/' + "notify.log"

    print "\nOnce you have checked the log file and generated emails"
    print "use the command below to send emails to all users:"
    print "\n./send_all_email.py -o " + work_dir + '/' + " [ -p smtp.unimelb.edu.au \
] [ -tr send_all_emails@to_this_test_address.com ]"

if __name__ == '__main__':
    main()
