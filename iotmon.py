#!/usr/local/bin/python -u

import sys,os,logging,re,traceback
sys.path.append("pymodules")
#sys.path.append("/usr/local/bin/pymodules")
from emgenutil import EXENAME,EXEPATH,GeneralError
import emgenutil,time
import sqlite3 as lite

#------------------------------------------------------------------------------
# GLOBALS
#------------------------------------------------------------------------------

logger=logging.getLogger(EXENAME)

#------------------------------------------------------------------------------
# USAGE
#------------------------------------------------------------------------------

def usage():
   from string import Template
   usagetext = """

 $EXENAME

 Function: Whatever

 Syntax  : $EXENAME {--debug #}

 Note    : Parm       Description
           ---------- --------------------------------------------------------
           --debug    optionally specifies debug option
                      0=off 1=STDERR 2=FILE

 Examples: $EXENAME

 Change History:
  em  XX/XX/2016  first written
.
"""
   template = Template(usagetext)
   return(template.substitute({'EXENAME':EXENAME}))


#------------------------------------------------------------------------------
# Subroutine: main
# Function  : Main routine
# Parms     : none (in sys.argv)
# Returns   : nothing
# Assumes   : sys.argv has parms, if any
#------------------------------------------------------------------------------
def main():

   ##############################################################################
   #
   # Main - initialize
   #
   ##############################################################################

   initialize()

   class State:
      DOWN    = "DOWN"
      UP      = "UP"
      UNKNOWN = "UNKNOWN"

   ##############################################################################
   #
   # Logic
   #
   ##############################################################################

   try:

      #-----------------------------------------------------------------------------------
      # Create database of  devices to be monitored and initialize to "UNKNOWN"
      #-----------------------------------------------------------------------------------

      db = lite.connect('%s%s.db' % (EXEPATH, EXENAME))
      # The default cursor returns the data in a tuple of tuples. When we use a dictionary cursor,
      # the data is sent in the form of Python dictionaries. This way we can refer to the data by their column names.
      db.row_factory = lite.Row

      with db:

         cursor = db.cursor()
         cursor.execute("DROP TABLE IF EXISTS Devices")
         cursor.execute("CREATE TABLE Devices(IpAddr TEXT PRIMARY KEY, Descr TEXT, State TEXT)")

         for device in G_config["IoTDevices"]:
            print(device, G_config["IoTDevices"][device])
            cursor.execute('INSERT INTO Devices VALUES ("%s", "%s","%s")' % (device, G_config['IoTDevices'][device], State.UNKNOWN))

         lid = cursor.lastrowid
         logger.info("The last Id of the inserted row is %d" % lid)

         logAllRowsInTable(cursor, "Devices")

         #-----------------------------------------------------------------------------------
         # Get into a monitor cycle
         #-----------------------------------------------------------------------------------

         updateCursor = db.cursor()
         while 1:

            logger.info("********** Starting a ping cycle *************")

            cursor.execute("SELECT * FROM Devices")
            for row in cursor:
               logger.info("Row Info: %(IpAddr)s, %(Descr)s, %(State)s" % row)
               # If device responds to ping...
               if emgenutil.ping(row['IpAddr']):
                  # if it was not UP prior to this, update the device state in the database and send out notification (if it was DOWN before)
                  if row['State'] != State.UP:
                     updateCursor.execute("UPDATE Devices SET State = '%s' WHERE IpAddr = '%s'" % (State.UP, row['IpAddr']))
                     if row['State'] == State.DOWN:
                        logger.info("State of %(IpAddr)s (%(Descr)s) has changed from DOWN to UP" % row)
                        print("Send email now: State of %(IpAddr)s (%(Descr)s) has changed from DOWN to UP" % row)
                     else:
                        # device is found to be up for the first time.  Just log that fact.  No notification.
                        logger.info("State of %(IpAddr)s (%(Descr)s) has changed from UNKNOWN to UP" % row)
               # if device did NOT respond to ping...
               else:
                  # if it was UP prior to this, update the device state in the databaes and send out notification (if it was UP before)
                  if row['State'] == State.UP:
                     logger.info("State of %(IpAddr)s (%(Descr)s) has changed from UP to DOWN" % row)
                     updateCursor.execute("UPDATE Devices SET State = '%s' WHERE IpAddr = '%s'" % (State.DOWN, row['IpAddr']))
                     print("Send email now: State of %(IpAddr)s (%(Descr)s) has changed from UP to DOWN" % row)

            logger.info("Sleeping for %d seconds..." % G_config["PingCycle"])
            time.sleep(G_config["PingCycle"])

   except GeneralError as e:
      if emgenutil.G_options.debug:
         # Fuller display of the Exception type and where the exception occured in the code
         (eType, eValue, eTraceback) = sys.exc_info()
         tbprintable = ''.join(traceback.format_tb(eTraceback))
         emgenutil.exitWithErrorMessage("%s Exception: %s\n%s" % (eType.__name__, eValue, tbprintable), errorCode=e.errorCode)
      else:
         emgenutil.exitWithErrorMessage(e.message, errorCode=e.errorCode)

   except Exception as e:
      if emgenutil.G_options.debug:
         # Fuller display of the Exception type and where the exception occured in the code
         (eType, eValue, eTraceback) = sys.exc_info()
         tbprintable = ''.join(traceback.format_tb(eTraceback))
         emgenutil.exitWithErrorMessage("%s Exception: %s\n%s" % (eType.__name__, eValue, tbprintable))
      else:
         emgenutil.exitWithErrorMessage(str(e))

   ##############################################################################
   #
   # Finish up
   #
   ##############################################################################

   logger.info(EXENAME+" exiting")
   logging.shutdown()

   exit()

# https://docs.python.org/3.3/library/sqlite3.html#sqlite3.Row
def logAllRowsInTable(cursor, tableName):
   cursor.execute("SELECT * FROM %s" % tableName)
   for row in cursor:
      msg = ''
      for key in row.keys():
         msg += "%s=%s," % (key,row[key])
      logger.info(msg)



#------------------------------------------------------------------------------
# Subroutine: initialize
# Function  : performs initialization of variable, CONSTANTS, other
# Parms     : none
# Returns   : nothing
# Assumes   : ARGV has parms, if any
#------------------------------------------------------------------------------
def initialize():

   # PROCESS COMMAND LINE PARAMETERS

   import argparse  # http://www.pythonforbeginners.com/modules-in-python/argparse-tutorial/

   parser = argparse.ArgumentParser(usage=usage())
   parser.add_argument('--debug', dest="debug", type=int, help='0=no debug, 1=STDERR, 2=log file')

   emgenutil.G_options = parser.parse_args()

   if emgenutil.G_options.debug == None or emgenutil.G_options.debug == 0:
      logging.disable(logging.CRITICAL)  # effectively disable all logging
   else:
      if emgenutil.G_options.debug == 9:
         emgenutil.configureLogging(loglevel='DEBUG')
      else:
         emgenutil.configureLogging()

   global G_config
   G_config = emgenutil.processConfigFile()

   logger.info(EXENAME+" starting:"+__name__+" with these args:"+str(sys.argv))

# Standard boilerplate to call the main() function to begin the program.
if __name__ == "__main__":
   main()

