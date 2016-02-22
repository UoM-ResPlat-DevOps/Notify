User email notification scripts.

The user email notification system is split in to two scripts.

1) ./generate_email.py create an outbox folder and fill it with generated emails according to the the specific details set by command line options and selected template.
2) ./send_all_emails.py Send all email from a specific outbox folder to the corresponding user email addresses.

Both scripts must be used together.

First we generate all the emails according to a specific outage scenario and a corresponding template file:
Templates are located in ./templates

usage: generate_email.py [-h] [-z TARGET_ZONE] [-n NODE] [--status STATUS]
                         [-tr TEST_RECIPIENT] [-p SMTP_SERVER] -st START_TIME
                         -d DURATION -tz TIMEZONE -t TEMPLATE

Example:

./generate_email.py -z melbourne-qh2 --status ACTIVE -st '10:00 24-02-2016' -d 2 -tz AEDT -n qh2-rcc94 -t single_node.tmpl

The command above will target all users of tenants correspoding to instances on node qh2-rcc94

Upon running the ./genearte_email.py command an outbox folder will be created. Each email to be sent to a user will be
stored in an individual file with the filename as the recipient address and the first line as the subject.
A log file is created for each outbox indicating which tenants are affected by the outage, which instances on which host 
beloning to the tenant, and a list of users who will recieve the outage email.

Once you have verified both the log file and the generated emails as being correct, you can then proceed to send
all the emails from the outbox folder using the following command:

usage: send_all_email.py [-h] [-p SMTP_SERVER] [-o OUTBOX]
                         [-tr TEST_RECIPIENT]

./sendallmail.py -o ./outbox/16-02-22_12:00:22/ -p smtp.unimelb.edu.au
