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
from subprocess import call, check_output
from shlex import quote

import pexpect

from pext_base import ModuleBase
from pext_helpers import Action


class Module(ModuleBase):
    def init(self, settings, q):
        self.binary = "todo.sh" if ('binary' not in settings) else settings['binary']

        self.q = q

        self.ANSIEscapeRegex = re.compile('(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')

        self._getCommands()
        self._getEntries()

    def _call(self, command, returnOutput=False):
        if returnOutput:
            return check_output([self.binary] + command).decode("utf-8")
        else:
            call([self.binary] + command)

    def _getSupportedCommands(self):
        return ["add", "addto", "append", "archive", "deduplicate", "rm", "depri", "do", "mv", "prepend", "pri", "replace"]

    def _getCommands(self):
        commandsStarted = False

        # We will crash here if todo.sh is not installed.
        # TODO: Find a nice way to notify the user they need to install todo.sh
        commandText = self._call(["-h"], returnOutput=True)

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
                    if variation in self._getSupportedCommands():
                        self.q.put([Action.addCommand, variation + " " + " ".join(lineData[1:])])

    def _getEntries(self):
        commandOutput = self.ANSIEscapeRegex.sub('', self._call(["ls"], returnOutput=True)).splitlines()

        for line in commandOutput:
            if line == '--':
                break

            self.q.put([Action.addEntry, line])

    def _runCommand(self, command):
        if command[0] not in self._getSupportedCommands():
            return None

        sanitizedCommandList = []
        for commandPart in command:
            sanitizedCommandList.append(quote(commandPart))

        command = " ".join(sanitizedCommandList)
        proc = pexpect.spawn('/bin/sh', ['-c', self.binary + " " + command])

        return self._processProcOutput(proc, command)

    def _processProcOutput(self, proc, command):
        result = proc.expect_exact([pexpect.EOF, pexpect.TIMEOUT, "(y/n)"], timeout=3)
        if result == 0:
            exitCode = proc.sendline("echo $?")
        elif result == 1:
            self.q.put([Action.addError, "Timeout error while running '{}'".format(command)])
            if proc.before:
                self.q.put([Action.addError, "Command output: {}".format(self.ANSIEscapeRegex.sub('', proc.before.decode("utf-8")))])

            return None
        else:
            proc.setecho(False)
            self.proc = {'proc': proc,
                         'command': command,
                         'type': Action.askQuestionDefaultNo}
            self.q.put([Action.askQuestionDefaultNo, proc.before.decode("utf-8")])

            return None

        proc.close()
        exitCode = proc.exitstatus

        message = self.ANSIEscapeRegex.sub('', proc.before.decode("utf-8")) if proc.before else ""

        self.q.put([Action.setFilter, ""])

        if exitCode == 0:
            # TODO: Only add new entry to list
            self.q.put([Action.replaceEntryList, []])
            self._getEntries()

            return message
        else:
            self.q.put([Action.addError, message if message else "Error code {} running '{}'. More info may be logged to the console".format(str(exitCode), command)])

            return None

    def stop(self):
        pass

    def selectionMade(self, selection):
        if len(selection) == 1:
            if selection[0]["type"] == "command":
                parts = selection[0]["value"].split(" ")
                self._runCommand(parts)
                self.q.put([Action.setSelection, []])
            elif selection[0]["type"] == "entry":
                self.q.put([Action.copyToClipboard, selection[0]["value"]])
                self.q.put([Action.close])

    def processResponse(self, response):
        self.proc['proc'].waitnoecho()
        self.proc['proc'].sendline('y' if response else 'n')
        self.proc['proc'].setecho(True)

        self._processProcOutput(self.proc['proc'], self.proc['command'])

