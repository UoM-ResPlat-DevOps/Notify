#!/usr/bin/env python

import os
import sys
import re
import argparse
import smtplib
import logging
import datetime
from collections import OrderedDict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# urgh globals
global smtp_server
global smtp_obj
global smtp_msgs_per_conn
global smtp_curr_msg_num
smtp_server = None
smtp_obj = None
smtp_msgs_per_conn = None
smtp_curr_msg_num = None

def collect_args():

    parser = argparse.ArgumentParser(
        description='Se')

    parser.add_argument('-p', '--smtp_server',
                        default='127.0.0.1',
                        help='SMTP server to use, defaults to localhost')
    parser.add_argument('-o', '--outbox',
                        required=False,
                        default=None,
                        help='Path to outbox folder containg emails to be sent')
    parser.add_argument('-tr', '--test_recipient',
                        required=False,
                        default=None,
                        help='send all emails to this single address, ignore recipient')
    return parser

def raise_error(error_msg):
    print error_msg
    sys.exit(1)


def get_datetime(dt_string):
    return datetime.datetime.strptime(dt_string, '%H:%M %d-%m-%Y')

def send_email(recipient, subject, text):

    global smtp_server
    global smtp_obj
    global smtp_msgs_per_conn
    global smtp_curr_msg_num

    msg = MIMEMultipart('alternative')
    msg.attach(MIMEText(text, 'plain', 'utf-8'))

    msg['From'] = 'NeCTAR Research Cloud <bounces@rc.nectar.org.au>'
    msg['To'] = recipient
    msg['Reply-to'] = 'support@nectar.org.au'
    msg['Subject'] = subject

    smtp_curr_msg_num += 1
    if smtp_curr_msg_num > smtp_msgs_per_conn:
        print "Resetting SMTP connection."
        try:
            smtp_obj.quit()
        except Exception as err:
            sys.stderr.write('Exception quit-ing SMTP:\n%s\n' % str(err))
        finally:
            smtp_obj = None

    if smtp_obj is None:
        smtp_curr_msg_num = 1
        smtp_obj = smtplib.SMTP(smtp_server)

    try:
        smtp_obj.sendmail(msg['From'], [recipient], msg.as_string())
    except smtplib.SMTPRecipientsRefused as err:
        sys.stderr.write('SMTP Recipients Refused:\n')
        sys.stderr.write('%s\n' % str(err))
    except smtplib.SMTPException:
        # could maybe do some retry here
        sys.stderr.write('Error sending to %s ...\n' % recipient)
        raise

def main():
    global smtp_server
    global smtp_obj
    global smtp_msgs_per_conn
    global smtp_curr_msg_num
    global test_recipient
    global tenant_data
    global total
    global user_data

    args = collect_args().parse_args()

    smtp_obj = None
    smtp_msgs_per_conn = 100
    smtp_curr_msg_num = 1
    smtp_server = args.smtp_server

    outbox = args.outbox


    #outbox = os.path.abspath(args.outbox-folder)
    print outbox
    if not os.path.isdir(outbox):
        raise_error("Outbox folder is not a valid path")
    
    os.chdir(outbox)
    sent = 0

    for root, dirs, files in os.walk('.', topdown=True):
        for email in files:
                if '@' in email:
                    with open(email, "r") as fh:
                        subject = fh.readline().split(':')[1][1:]
                        body = fh.read()
                        if args.test_recipient:
                            print "Sending to: " + email + " (actual recipient: " + args.test_recipient + ")"
                            send_email(args.test_recipient, subject, body)
                        else:
                            print "Sending to: " + email
                            send_email(email, subject, body)

    proceed = False
    


if __name__ == '__main__':
    main()
