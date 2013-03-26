#!/usr/bin/python
import imaplib, smtplib, email
import base64, getpass, time
import fcntl, subprocess, os
import string, getopt, sys

from email.parser import HeaderParser
from threading import Thread

def non_block_read(output):
    ''' even in a thread, a normal read with block until the buffer is full '''
    fd = output.fileno()
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    try:
        return output.read()
    except:
        return ''

def log_worker(stdout, log_buffer):
    ''' needs to be in a thread so we can read the stdout w/o blocking '''
    while True:
        output = non_block_read(stdout)
        if output:
            print output
            log_buffer.append(output)

def get_first_text_block(email_message_instance):
    maintype = email_message_instance.get_content_maintype()
    if maintype == 'multipart':
        for part in email_message_instance.get_payload():
            if part.get_content_maintype() == 'text':
                try:
                     return base64.decodestring(part.get_payload())
                except:
                     return part.get_payload()
    elif maintype == 'text':
        return email_message_instance.get_payload()


def usage():
    print "Usage:"
    print "-i: IMAP server"
    print "-s: SMTP server"
    print "-a: e-mail address"
    print "-t: check interval"               
    sys.exit(2)

try:                                
    opts, args = getopt.getopt(sys.argv[1:], "i:s:a:t:") 
except getopt.GetoptError:           
    usage()

imapserver = ""
smtpserver = ""
email_address = ""
interval = ""

for opt, arg in opts:         
    if opt == "-i":      
        imapserver = arg                 
    elif opt == "-s":                
        smtpserver = arg                     
    elif opt == "-a":                
        email_address = arg                
    elif opt == "-t":                
        interval = float(arg)

if imapserver == "" or smtpserver == "" or email_address == "" or interval == "":
    usage()

password = getpass.getpass('Your IMAP password: ')
secret_key = getpass.getpass('Your secret key: ')

mail = imaplib.IMAP4_SSL(imapserver)
mail.login(email_address, password)
blacklist = []

process = subprocess.Popen(['/bin/bash'], shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
log_buffer = []
thread = Thread(target=log_worker, args=[process.stdout, log_buffer])
thread.daemon = True
thread.start()

while 1:
    mail.list()
    mail.select("inbox")                    # connect to inbox.
    result, data = mail.search(None, "ALL")
    ids = data[0]                           # data is a list.
    id_list = ids.split()                   # ids is a space separated string
    latest_email_id = id_list[-1]           # get the latest
    if latest_email_id in blacklist:
        continue

    # only peek at header
    msg_data = mail.fetch(latest_email_id, '(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM)])')
    header_data = msg_data[1][0][1]
    parser = HeaderParser()
    msg = parser.parsestr(header_data)
    
    if (msg['Subject'] == "ImapExecuter"):
        result, data = mail.fetch(latest_email_id, "(RFC822)")  # fetch the email body (RFC822) for the given ID
        raw_email = data[0][1]                                  # here's the body, which is raw text of the whole email
        email_message = email.message_from_string(raw_email)
        email_content = get_first_text_block(email_message)
        lines = email_content.split("\n")
        lines = [line for line in lines if line.strip()]
        if (lines[0].strip() == secret_key):
            mail.store(latest_email_id, '+FLAGS', '\\Deleted')
            mail.expunge()
            for line in lines:
                if line.strip() == "SEND_LOG":
                    print "Sending log"
                    server = smtplib.SMTP(smtpserver, 587)
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(email_address, password)
                    body = string.join((
                        "From: %s" % email_address,
                        "To: %s" % msg['From'],
                        "Subject: %s" % "ImapExecuter log",
                        "",
                        "".join(log_buffer)), "\r\n")
                    server.sendmail(email_address, [msg['From']], body)
                    log_buffer = []
                    server.close()
                elif (line.strip() != secret_key and line.strip() != ""):
                    print "[ImapExecuter]$ " + line.strip()
                    process.stdin.write(line.strip() + "\n")
        else:
            print "Invalid secret key '%s' received from %s!" % (msg['From'], lines[0].strip())
            blacklist.append(latest_email_id)
        
    time.sleep(interval)



