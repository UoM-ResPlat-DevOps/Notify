#!/usr/bin/env python
# Author: Justin Mammarella
# Date:   22/02/2016
# Description: Email generator for user notification.
#             Based on nectar-tools/announce
# Updated: 26/06/2017
# Author: Nhat Ngo

import os
import sys
import re
import argparse
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
    parser.add_argument('-n', '--nodes',
                        default=None,
                        help='Only target instances from the following Hosts/Nodes\
                              (e.g. qh2-rcc1 or qh2-rcc[10-99,101])')
    parser.add_argument('--status',
                        default=None,
                        help='Only consider instances with status')
    parser.add_argument('-tr', '--test_recipient',
                        default=None,
                        help='Only generate a notification for this \
                              email address')
    parser.add_argument('--subject',
                        help='Custom email subject')
    parser.add_argument('-st', '--start_time', action='store',
                        type=get_datetime,
                        help='Outage start time (e.g. \'09:00 25-06-2015\')')
    parser.add_argument('-d', '--duration', action='store', type=int,
                        help='Duration of outage in hours')
    parser.add_argument('-tz', '--timezone', action='store', default='AEDT',
                        help='Timezone (e.g. AEDT)')
    parser.add_argument('-t', '--template', action='store',
                        help='Name of template to use. Templates to be\
                              stored in ./template/',
                        required=True)
    parser.add_argument('-f', '--file',
                        default=None,
                        help='Only consider instances with given id\
                              listed in FILE')

    return parser


def get_datetime(dt_string):
    return datetime.datetime.strptime(dt_string, '%H:%M %d-%m-%Y')


def create_notification(user, start_ts, end_ts, tz, zone, nodes,
                        test_recipient, work_dir, template, custom_subject):
    instances = user['instances']
    email = user['email']
    name = user['name']
    enabled = user['enabled']
    subject = 'NeCTAR Research Cloud outage'
    if custom_subject:
        subject = custom_subject
    affected_instances = 0
    for project, servers in instances.iteritems():
        for server in servers:
            affected_instances += 1

    affected = bool(affected_instances)
    if affected and not custom_subject:
        subject += ' concerning your instances'

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
                         zone, affected, nodes, work_dir + '/' + email,
                         template)
        return True

    return False


def render_templates(subject, instances, start_ts, end_ts, tz, zone,
                     affected, nodes, filename, template):

    duration = end_ts - start_ts if start_ts and end_ts else None
    days = duration.days if duration else None
    hours = duration.seconds//3600 if duration else None

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
                     'nodes': nodes,
                     'affected': affected})
    with open(filename, "wb") as fh:
        fh.write("Subject: " + subject + '\n')
        fh.write(text)

    return text


def send_email(recipient, subject, text, html):
    return 0


def parse_nodes(nodes):
    # Parse list syntax (eg. qh2-rcc[01-10,13])
    # If there is only one node (eg. qh2-rc101)
    splitted_nodes = nodes.split('[')
    if len(splitted_nodes) == 1:
        return [splitted_nodes[0]]
    # Multiple [] not supported
    elif len(splitted_nodes) > 2:
        raise ValueError('--nodes {0}: Multiple [] not supported.'.format(nodes))
    else:
        prefix, suffix = splitted_nodes
        values, suffix = suffix.split(']')
        # Handle value within the [] brackets
        values = values.split(',')
        unpacked_values = []
        for value in values:
            # If comma separated. Eg: [123, 126]
            if len(value.split('-')) == 1:
                unpacked_values.append(int(value))
            # If have dash, make a list. Eg: [127-130]
            else:
                start, end = value.split('-')
                unpacked_values.extend(range(int(start.strip(' ')), int(end.strip(' ')) + 1))
        return [prefix + str(value) + suffix for value in set(unpacked_values)]


def get_instances(client, zone=None, inst_status=None, nodes=None):
    marker = None
    # Collect instances for the following nodes
    if nodes:
        nodes_list = parse_nodes(nodes)
        opts = {'all_tenants': True}
        if inst_status is not None:
            opts['status'] = inst_status
        for host in nodes_list:
            opts['host'] = host
            response = client.servers.list(search_opts=opts)
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


def get_instances_from_file(client, filename):
    with open(filename, 'r') as server_ids:
        for server_id in server_ids:
            yield client.servers.get(server_id.strip('\n'))


def populate_tenant(keystone, tenant, tenant_data):
    users = get_users(keystone, tenant)
    name = tenant.name
    if tenant.id not in tenant_data:
        tenant_data[tenant.id] = {'users': users, 'instances': []}
    else:
        tenant_data[tenant.id]['users'] = users
    tenant_data[tenant.id]['name'] = name


def generate_log(user_data, tenant_data):
    for t in tenant_data:
        affected_instances = len(t.instances)
        output_text(" ")
        display_break('=')
        display_column(t.name, t.id)
        display_break('=')
        output_text("Affected instances: ")
        output_text(" ")
        for instance in t.instances:
            zone = getattr(instance, 'OS-EXT-AZ:availability_zone')
            node = getattr(instance, 'OS-EXT-SRV-ATTR:host')
            display_column(instance.name[:40], instance.id, node, zone)
        display_break(' ')

        for t_u in t.users:
            for id, user in  user_data.iteritems():
                if t_u.id == id:
                    display_column(str(user['email'])[:40])


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
    nc = nova_client.Client(2, session=sess)

    zone = args.target_zone
    inst_status = args.status
    test_recipient = args.test_recipient

    start_ts = args.start_time
    end_ts = start_ts + datetime.timedelta(hours=args.duration)\
             if start_ts else None

    template = args.template
    nodes = args.nodes
    subject = args.subject

    server_ids_file = args.file

    # Parameters checking
    if not server_ids_file:
        if not start_ts:
            print """No -st START_TIME: Please specify an outage start time.
                        (e.g. '09:00 25-06-2015')"""
            sys.exit(2)
        if not end_ts:
            print "No -d DURATION: Please specify an outage duration in hours."
            sys.exit(2)

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
    affected_instances = list(get_instances_from_file(nc, server_ids_file)
                              if server_ids_file
                              else get_instances(nc, zone, inst_status, nodes))

    # List tenants associated with affected instances
    affected_tenants = set([instance.tenant_id for instance in affected_instances])

    print "Collecting projects"
    # Tenant data
    tenants = kc.projects.list()

    # For each affected tenant get the users in the tenant
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

    # Add affected instance objects to tenants.

    for instance in affected_instances:
        for t in tenant_list:
            if t.id == instance.tenant_id:
                t.instances.append(instance)

    print "Gathering tenant information."
    proceed = False

    # Create a list of affected users and associated instances

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

    generate_log(user_data, tenant_list)

    print "Generating notification emails."
    count = 0
    proceed = False

    for uid, user in user_data.iteritems():
        if test_recipient:
            # Generate emails for only one email address
            if user['email'] == test_recipient:
                if create_notification(user, start_ts, end_ts,
                                       args.timezone, zone, args.nodes,
                                       test_recipient, work_dir,
                                       template, subject):
                    count += 1
        else:
            if create_notification(user, start_ts, end_ts, args.timezone,
                                   zone, args.nodes, test_recipient, work_dir,
                                   template, subject):
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
