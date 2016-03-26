#!/usr/local/bin/python
###########################################################################
#
# emgenutil.py
#
# Function: Python Utility functions
#
# Change History:
#  edm  11/21/2013  first written
#
###########################################################################
#
import sys,os,logging,subprocess,re,datetime,yaml

# Import smtplib for the actual sending function
import smtplib

# Import the email modules we'll need
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders

# import socket for singleton lock
import socket


#------------------------------------------------------------------------------
# CLASSES
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
# Class: GeneralError
# Function  : Handle exceptions raised for general errors encountered
# Parms     : message - some error message string
#             errorCode - an optional HTTP Error code
# Returns   : __str__ returns an appropriate error message
# Assumes   :
#------------------------------------------------------------------------------
class GeneralError(Exception):
   def __init__(self, message, errorCode="400 Bad Request"):
       self.message = message
       self.errorCode = errorCode
   def __str__(self):
      return "Error encountered!  %s  errorCode=%s." % (self.message, self.errorCode)

#------------------------------------------------------------------------------
# GLOBALS
#------------------------------------------------------------------------------

logger=logging.getLogger(__name__)

G_options = None  # options from the cmd line (argparse object)
G_config  = {}    # options from the script's ini file

(EXEPATH,EXENAME) = os.path.split(sys.argv[0])
EXEPATH += os.sep

#------------------------------------------------------------------------------
# Function  : configureLogging
# Function  : configures the Logging for this execution of the program
# Parms     : logdestination = (optional) 'STDERR' or the name of a file to log to
#                 defaults to sys.argv[0].log
#             loglevel = lowest level of message to log.
#                 defaults to 'INFO'
# Returns   : nothing
# Assumes   :
#------------------------------------------------------------------------------
def configureLogging(logdestination=sys.argv[0]+'.log',loglevel='INFO'):
   if G_options.debug == 1:
      logging.basicConfig(
         format='%(asctime)s %(name)s:%(lineno)i %(levelname)s %(message)s',
         datefmt='%m/%d/%Y %H:%M:%S',
         level=getattr(logging, loglevel.upper())
      )
   else:
      # Need to do this vs. using basicConfig because we need latin-1 encoding to prevent unexpected data errors writing to the log
      root_logger= logging.getLogger()
      root_logger.setLevel(getattr(logging, loglevel.upper()))
      handler = logging.FileHandler(logdestination, 'w', 'latin-1')
      formatter = logging.Formatter('%(asctime)s %(name)s:%(lineno)i %(levelname)s %(message)s')
      handler.setFormatter(formatter)
      root_logger.addHandler(handler)

#------------------------------------------------------------------------------
# Function  : execCommand
# Function  : executes a shell command
# Parms     : cmd = string, command(s) to exec (can be anything that the shell will accept)
# Returns   : tuple: (returncode,stdout,stderr)
# Assumes   :
#------------------------------------------------------------------------------
def execCommand(cmd):

   proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
   (out, err) = proc.communicate()
   return(proc.returncode,out,err)



#------------------------------------------------------------------------------
# Function  : processConfigFile
# Function  : Reads Config file and establishes G_config dict with values.
#             Config file is yaml syntax.
# Parms     : none
# Returns   : nothing
# Assumes   : Config file is in the same dir as executable and named $EXENAME.yaml
#
# Example of what calling module can do with G_config
#  for key in emgenutil.G_config:
#     print(key+":"+emgenutil.G_config[key]+".")
#  mylist = emgenutil.G_config['listoption'].splitlines()
#  print(mylist)
#
#------------------------------------------------------------------------------
def processConfigFile(configFile=sys.argv[0]+".ini"):

   global G_config

   if not os.path.isfile(configFile):
      errorexit("config file "+configFile+" not found.",2);

   config = yaml_load(configFile)

   for key in G_config:
      logger.info("G_config["+key+"]:"+G_config[key]+".")


#------------------------------------------------------------------------------
# Function  : ping
# Function  : Attempt to ping a device.
# Parms     : nameOrIP - hostname or IP adddress
#             count - # of pings to try (optional)
# Returns   : True (responded to ping) or False (100% packet loss)
# Assumes   :
#------------------------------------------------------------------------------
def ping(nameOrIP,count=2):

   cmd = '/bin/ping -c%d %s' % (count, nameOrIP)

   proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
   (out, err) = proc.communicate()

   #print(out)

   if " 100% packet loss" in out or "unknown host" in err:
      return False

   if "%d packets transmitted" % count in out:
      return True

   errorexit("ERROR: unexpected results from ping.  %s" % out)


#------------------------------------------------------------------------------
# Function  : getLock
# Function  : Attempt to get a lock on a given lock name.
# Parms     : lockName - a unique string to represent the lock
# Returns   : nothing.  Raises a GeneralError if the lock cannot be obtained.
# Assumes   : This will only be used for a single held lock at a time.
#             A freeLock must be done before obtaining a new lock.
#------------------------------------------------------------------------------
import socket
def getLock(lockName):
  global G_lockSocket   # Without this our lock gets garbage collected (refereneced by freeLock too)
  G_lockSocket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
  try:
    G_lockSocket.bind('\0' + lockName)
    logger.info('Lock %s successfully obtained.' % lockName)
  except socket.error as e:
    logger.info('Lock %s exists so another script must have it.' % lockName)
    raise GeneralError("Lock %s already in use." % lockName)

#------------------------------------------------------------------------------
# Function  : getLock
# Function  : Frees the lock obtained by getLock
# Parms     : none
# Returns   : nothing
# Assumes   : G_lockSocket is the socket created by getLock.
#------------------------------------------------------------------------------
def freeLock():
   G_lockSocket.shutdown(socket.SHUT_RDWR)
   G_lockSocket.close()


#------------------------------------------------------------------------------
# Function  : yaml_load
# Function  : Load yaml data from a file
# Parms     : filename
# Returns   : data structure as per the yaml file
# Assumes   :
#------------------------------------------------------------------------------
def yaml_load(filepath):
   with open(filepath, "r") as INFILE:
      data = yaml.load(INFILE)
   return data




def sendEmail(emailTo, subject, bodyText, bodyHtml=None, binaryFilename=None):

   #---------------------------------------------------------------------------
   # Send an email with a file attachment
   #---------------------------------------------------------------------------

   hostname   = os.uname().nodename
   emailFrom  = 'donotreply@%s' % hostname

   # Create the enclosing (outer) message
   msg = MIMEMultipart()
   msg['Subject'] = subject
   msg['To'] = emailTo
   msg['From'] = emailFrom
   msg.preamble = 'You will not see this in a MIME-aware mail reader.\n'
   msg.attach(MIMEText(bodyText))
   if bodyHtml:
   		msg.attach(MIMEText(bodyHtml,'html'))

   if binaryFilename:
      ctype = 'application/octet-stream'
      maintype, subtype = ctype.split('/', 1)
      with open(binaryFilename,"rb") as INFILE:
         fileAttachment = MIMEBase(maintype, subtype)
         fileAttachment.set_payload(INFILE.read())

      # Encode the payload using Base64
      encoders.encode_base64(fileAttachment)

      # Set the filename parameter and attach file to outer message
      fileAttachment.add_header('Content-Disposition', 'attachment', filename=binaryFilename)
      msg.attach(fileAttachment)
      msg.attach(MIMEText('This file is attached: %s' % binaryFilename))

   # Now send the message
   mailServer = smtplib.SMTP('smtp.gmail.com:587')
   mailServer.starttls()
   mailServer.login(G_config['sendEmail']['gmailUsername'],G_config['sendEmail']['gmailPassword'])

   mailServer.sendmail(emailFrom, emailTo, msg.as_string())
   mailServer.quit()

#------------------------------------------------------------------------------
# Initialize
#------------------------------------------------------------------------------

G_config = yaml_load("emgenutil.yaml")

#------------------------------------------------------------------------------
# main
#------------------------------------------------------------------------------

if __name__ == "__main__":

   print("Starting...");
   print("Config items: %s" % str(G_config))

   print("Sending a test email...")
   subject = 'This is a test email sent at %s!' % datetime.datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
   bodyText = "This is the body\nAnd more"
   emailTo = "edminernew@gmail.com"
   sendEmail(emailTo, subject, bodyText, "/etc/hosts")

   print(EXENAME,EXEPATH,ping('google.com'))
   (returncode,out,err) = execCommand('ls -la')
   print("returncode = %d. stdout = %s. stderr = %s." % (returncode,out,err))
   print("Done")

