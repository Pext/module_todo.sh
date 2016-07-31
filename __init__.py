#!/usr/bin/env python3

# Pext todo.sh module is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re

from os.path import expanduser
from subprocess import call, check_output, Popen, PIPE
from shlex import quote

import pexpect

from pext_base import ModuleBase
from pext_helpers import Action


class Module(ModuleBase):
    def init(self, binary, q):
        self.binary = "todo.sh" if (binary is None) else binary

        self.q = q

        self.getCommands()
        self.getEntries()

        self.ANSIEscapeRegex = re.compile('(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')

    def stop(self):
        pass

    def getDataLocation(self):
        return expanduser("~") + "/.todo/todo.txt"

    def call(self, command, returnOutput=False):
        if returnOutput:
            return check_output([self.binary] + command).decode("utf-8")
        else:
            call([self.binary] + command)

    def getSupportedCommands(self):
        return ["add", "addto", "append", "archive", "deduplicate", "rm", "depri", "do", "mv", "prepend", "pri", "replace"]

    def getCommands(self):
        commandsStarted = False

        # We will crash here if todo.sh is not installed.
        # TODO: Find a nice way to notify the user they need to install todo.sh
        commandText = self.call(["-h"], returnOutput=True)

        for line in commandText.splitlines():
            strippedLine = line.lstrip()
            if not commandsStarted:
                if strippedLine.startswith("Actions:"):
                    commandsStarted = True

                continue
            else:
                if strippedLine == '':
                    break

                lineData = strippedLine.split(" ")
                for variation in lineData[0].split("|"):
                    for supportedCommand in self.getSupportedCommands():
                        self.q.put([Action.addCommand, [supportedCommand, variation + " " + " ".join(lineData[1:])]])

    def getEntries(self):
        commandOutput = self.ANSIEscapeRegex.sub('', self.call(["ls"], returnOutput=True)).splitlines()

        for line in commandOutput:
            if line == '--':
                break

            self.q.put([Action.addEntry, [line, line]])

    def getAllEntryFields(self, entryName):
        return ['']

    def runCommand(self, command, printOnSuccess=False, hideErrors=False):
        sanitizedCommandList = []
        for commandPart in command:
            sanitizedCommandList.append(quote(commandPart))

        proc = pexpect.spawn('/bin/sh', ['-c', self.binary + " " + " ".join(sanitizedCommandList) + (" 2>/dev/null" if hideErrors else "")])
        return self.processProcOutput(proc, printOnSuccess, hideErrors)

    def processProcOutput(self, proc, printOnSuccess=False, hideErrors=False):
        result = proc.expect_exact([pexpect.EOF, pexpect.TIMEOUT, "(y/n)"], timeout=3)
        if result == 0:
            exitCode = proc.sendline("echo $?")
        elif result == 1 and proc.before:
            self.q.put([Action.addError, "Timeout error while running '{}'. This specific way of calling the command is most likely not supported yet by Pext.".format(" ".join(command))])
            self.q.put([Action.addError, "Command output: {}".format(self.ANSIEscapeRegex.sub('', proc.before.decode("utf-8")))])
        else:
            proc.setecho(False)
            self.proc = {'proc': proc,
                         'type': Action.askQuestionDefaultNo,
                         'printOnSuccess': printOnSuccess,
                         'hideErrors': hideErrors}
            self.q.put([Action.askQuestionDefaultNo, proc.before.decode("utf-8")])

            return

        proc.close()
        exitCode = proc.exitstatus

        message = self.ANSIEscapeRegex.sub('', proc.before.decode("utf-8")) if proc.before else ""

        self.q.put([Action.setFilter, ""])

        if exitCode == 0:
            if printOnSuccess and message:
                self.q.put([Action.addMessage, message])

            self.q.put([Action.replaceEntryList, self.getEntries()])

            return message
        else:
            self.q.put([Action.addError, message if message else "Error code {} running '{}'. More info may be logged to the console".format(str(exitCode), " ".join(command))])

            return None

    def processResponse(self, response):
        self.proc['proc'].waitnoecho()
        self.proc['proc'].sendline('y' if response else 'n')
        self.proc['proc'].setecho(True)

        self.processProcOutput(self.proc['proc'], printOnSuccess=self.proc['printOnSuccess'], hideErrors=self.proc['hideErrors'])

