User email notification system.
--------------------------------
The user email notification system consists of two scripts that must be 
used in conjunction with one another.

**1) generate_email.py:** 

Create an outbox folder and fill it with generated emails according to a 
selected template and the specific details set by command line options.

Usage:
> generate_email.py [-h] [-z TARGET_ZONE] [-n NODE] [--status STATUS] 
> [-tr TEST_RECIPIENT] [-p SMTP_SERVER] -st START_TIME -d DURATION 
> -tz TIMEZONE -t TEMPLATE

Example:

`./generate_email.py -z melbourne-qh2 --status ACTIVE -st '10:00 24-02-2016' -d 2 -tz AEDT -n qh2-rcc94 -t single_node.tmpl`

*The command above will generate emails for all users of each tenant 
corresponding to ACTIVE instances on the compute node qh2-rcc94.*

Templates are to be stored in the ./templates directory

Upon running ./generate_email.py an outbox folder will be created in the format
./outbox/DATE_TIME. Each generated email will be stored in an individual file. 
The filename of the email will be the recipient address and the content of the 
first line as the email subject.

A log file is created for each outbox indicating which tenants are affected,
under each tenant any affected instances are listed , and a list of users 
who will receive the outage email.

**2) ./send_all_email.py:** 

Once you have verified the output from ./generate_email.py as being correct 
(both the generated emails and log files), you can then proceed to send all 
the emails from the outbox folder using the following command:

usage: send_all_email.py [-h] [-p SMTP_SERVER] [-o OUTBOX]
                         [-tr TEST_RECIPIENT]

`./send_all_email.py -p smtp.unimelb.edu.au`-o ./outbox/16-02-22_12:00:22/ 

The optional TEST_RECIPIENT parameter will ignore the recipient email address 
associated with each email, and instead flood all emails to a single, 
specified address.
