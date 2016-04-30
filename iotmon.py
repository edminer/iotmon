#!/usr/local/bin/python -u

import sys,os,logging,re,traceback
(EXEPATH,EXENAME) = os.path.split(sys.argv[0])
EXEPATH += os.sep

sys.path.append("%spymodules" % EXEPATH)
from emgenutil import GeneralError,sendEmail
import emgenutil,time,datetime
import sqlite3 as lite

#------------------------------------------------------------------------------
# GLOBALS
#------------------------------------------------------------------------------

logger=logging.getLogger(EXENAME)
G_lastConfigModifyTime = None

class State:
   UP      = "UP"
   PENDING = "PENDING"
   DOWN    = "DOWN"
   UNKNOWN = "UNKNOWN"

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

   global G_lastConfigModifyTime
   global G_config
   initialize()
   todaysDate = None

   ##############################################################################
   #
   # Logic
   #
   ##############################################################################

   try:

      # We only want 1 instance of this running.  So attempt to get the "lock".
      emgenutil.getLock(EXENAME)

      #-----------------------------------------------------------------------------------
      # Create database of  devices to be monitored and initialize to "UNKNOWN"
      #-----------------------------------------------------------------------------------

      db = lite.connect('%s%s.db' % (EXEPATH, EXENAME))
      # The default cursor returns the data in a tuple of tuples. When we use a dictionary cursor,
      # the data is sent in the form of Python dictionaries. This way we can refer to the data by their column names.
      db.row_factory = lite.Row

      with db:

         cursor = db.cursor()

         initLogTable(cursor)

         #-----------------------------------------------------------------------------------
         # Get into a monitor cycle
         #-----------------------------------------------------------------------------------

         while 1:

            # see if the config file was modified
            currentConfigModifyTime = os.path.getmtime('%s%s.yaml' % (EXEPATH, EXENAME))
            if currentConfigModifyTime != G_lastConfigModifyTime:
               logger.info("Config modified.  Re-initing the database...")
               # re-read the config data
               G_config = emgenutil.processConfigFile()
               # re-init the database
               initDevicesTable(cursor)
               G_lastConfigModifyTime = currentConfigModifyTime

            # see if we have started into a new day
            if todaysDate != datetime.date.today():
               # every day, purge old log records
               purgeLogRecords(cursor)
               todaysDate = datetime.date.today()

            logger.info("********** Starting a ping cycle *************")

            cursor.execute("SELECT * FROM Devices")
            rows = cursor.fetchall()
            for row in rows:
               logger.info("Device Info: %(IPAddr)s, %(Descr)s, %(State)s, %(LastStateChange)s, %(SuppressCount)d, %(CurrentSuppressCount)d" % row)
               # If device responds to ping...
               if emgenutil.ping(row['IPAddr']):
                  # if it was not UP prior to this, update the device state in the database and send out notification (if it was DOWN before)
                  if row['State'] != State.UP:
                     cursor.execute("UPDATE Devices SET State=?, LastStateChange=?, CurrentSuppressCount=? WHERE IPAddr=?", (State.UP, str(datetime.datetime.today()), row['SuppressCount'], row['IPAddr']))
                     writeLogRecord(cursor, row['IPAddr'], row['Descr'], row['State'], State.UP)
                     if row['State'] == State.DOWN:
                        msg = "State of %(Descr)s (%(IPAddr)s) has changed from DOWN to UP" % row
                        logger.info("Sending email: %s" % msg)
                        sendEmail(G_config["NotifyEmail"], msg, "UP now, just FYI.")
                     else:
                        # device is found to be up for the first time.  Just log that fact.  No notification.
                        logger.info("State of %(IPAddr)s (%(Descr)s) has changed from UNKNOWN/PENDING to UP" % row)
               # if device did NOT respond to ping...
               else:
                  # if it was UP/PENDING prior to this, update the device state in the databaes and send out notification
                  # that device is DOWN if the CurrentSuppressCount is down to 0
                  if row['State'] == State.UP or row['State'] == State.PENDING:
                     if row['CurrentSuppressCount'] == 0:
                        msg = "State of %(Descr)s (%(IPAddr)s) has changed from UP to DOWN" % row
                        logger.info("Sending email: %s" % msg)
                        cursor.execute("UPDATE Devices SET State =?, LastStateChange =? WHERE IPAddr =?", (State.DOWN, str(datetime.datetime.today()), row['IPAddr']))
                        sendEmail(G_config["NotifyEmail"], msg, "DOWN!  Please investigate.")
                        writeLogRecord(cursor, row['IPAddr'], row['Descr'], row['State'], State.DOWN)
                     else:
                        currentSuppressCount = row['CurrentSuppressCount'] - 1
                        logger.info("Decrementing CurrentSuppressCount for %s to %s" % (row['IPAddr'], currentSuppressCount))
                        cursor.execute("UPDATE Devices SET State =?, CurrentSuppressCount =? WHERE IPAddr =?", (State.PENDING, currentSuppressCount, row['IPAddr']))
                        if row['State'] != State.PENDING:
                           writeLogRecord(cursor, row['IPAddr'], row['Descr'], row['State'], State.PENDING)
            db.commit()

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


def initLogTable(cursor):
   cursor.execute("CREATE TABLE IF NOT EXISTS Log (LogDate TEXT, IPAddr TEXT, Descr TEXT, PreviousState TEXT, CurrentState TEXT)")


def writeLogRecord(cursor, IPAddr, descr, previousState, currentState):
   cursor.execute('INSERT INTO Log VALUES (?,?,?,?,?)', (str(datetime.datetime.today()), IPAddr, descr, previousState, currentState))

def purgeLogRecords(cursor):
   cursor.execute("DELETE FROM Log WHERE LogDate < ?", (str(datetime.date.today() - datetime.timedelta(days=G_config["LogPurgeTimeframe"])),))


def initDevicesTable(cursor):

   cursor.execute("DROP TABLE IF EXISTS Devices")
   cursor.execute("CREATE TABLE Devices(IPAddr TEXT PRIMARY KEY, Descr TEXT, State TEXT, LastStateChange TEXT, SuppressCount INTEGER, CurrentSuppressCount INTEGER)")

   for device in G_config["IoTDevices"]:
      device['LastStateChange'] = str(datetime.datetime.today())
      device['state'] = State.UNKNOWN
      device['SuppressCount'] = device.get("SuppressCount",G_config["DefaultSuppressCount"])
      print(device)
      cursor.execute('INSERT INTO Devices VALUES (:IPAddr, :Description, :state, :LastStateChange, :SuppressCount, :SuppressCount)', device)

   lid = cursor.lastrowid
   logger.info("The last Id of the inserted row is %d" % lid)

   logAllRowsInTable(cursor, "Devices")


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

