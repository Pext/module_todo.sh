#!/usr/bin/env python3

# Copyright (C) 2016 - 2017 Sylvia van Os <sylvia@hackerchick.me>
#
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

from os.path import expanduser

from pext_base import ModuleBase
from pext_helpers import Action, SelectionType


class Module(ModuleBase):
    def init(self, settings, q):
        self.q = q

        self.todo_location = expanduser("~/todo.txt") if ('todo_file' not in settings) else expanduser(settings['todo_file'])
        self.done_location = expanduser("~/done.txt") if ('done_file' not in settings) else expanduser(settings['done_file'])

        self.entries = []
        self.actively_editing = None

        self._get_commands()
        self._get_entries()

    def _get_supported_commands(self):
        return ["add", "addto", "archive", "edit", "rm", "prepend", "replace"]

    def _get_commands(self):
        self.q.put([Action.replace_command_list, self._get_supported_commands()])

    def _get_entries(self):
         with open(self.todo_location) as todo_file:
            for line in todo_file:
                line = line.strip()
                if line:
                    self.entries.append(line)
                    self.q.put([Action.add_entry, "{} {}".format(len(self.entries), line)])

    def _reload_ui_list(self):
        self.q.put([Action.replace_entry_list, []])
        for number, entry in enumerate(self.entries):
            self.q.put([Action.add_entry, "{} {}".format(number + 1, entry)])

    def _get_entry_by_id(self, number):
        return self.entries[int(number) - 1]

    def _set_entry_by_id(self, number, value):
        self.entries[int(number) - 1] = value

    def _run_command(self, command):
        if command[0] not in self._get_supported_commands():
            return None

        # Set number and loaded_entry for commands that use an entry
        if command[0] in ["addto", "archive", "edit", "rm", "replace"]:
            number = int(command[1]) - 1

            try:
                loaded_entry = self.entries[number]
            except Exception as e:
                print(e)
                self.q.put([Action.add_error, "There is no entry with id {}".format(command[1])])
                return
 
        if command[0] == "add":
            entry = " ".join(command[1:])
            self.entries.append(entry)

            with open(self.todo_location, 'a') as todo_file:
                todo_file.write(entry + '\n')

        elif command[0] == "addto":
            entry = "{} {}".format(loaded_entry, " ".join(command[2:]))
            self.entries[number] = entry

            with open(self.todo_location, 'w') as todo_file:
                todo_file.writelines(entry + '\n' for entry in self.entries)

        elif command[0] == "archive":
            self.entries.remove(loaded_entry)
            
            with open(self.done_location, 'a') as done_file:
                done_file.write(loaded_entry + '\n')
            
            with open(self.todo_location, 'w') as todo_file:
                todo_file.writelines(entry + '\n' for entry in self.entries)

        elif command[0] == "edit":
            self.actively_editing = number
            self.q.put([Action.ask_input, "Editing {}: {}".format(number + 1, loaded_entry), loaded_entry])

        elif command[0] == "rm":
            self.entries.remove(loaded_entry)

            with open(self.todo_location, 'w') as todo_file:
                todo_file.writelines(entry + '\n' for entry in self.entries)

        elif command[0] == "prepend":
            entry = " ".join(command[1:])
            self.entries = [entry] + self.entries

            with open(self.todo_location, 'w') as todo_file:
                todo_file.writelines(entry + '\n' for entry in self.entries)

        elif command[0] == "replace":
            new_text = " ".join(command[2:])
            self.entries[number] = new_text

            with open(self.todo_location, 'w') as todo_file:
                todo_file.writelines(entry + '\n' for entry in self.entries)

    def process_response(self, response):
        if response is not None:
            self.entries[self.actively_editing] = response

            with open(self.todo_location, 'w') as todo_file:
                todo_file.writelines(entry + '\n' for entry in self.entries)

            self._reload_ui_list()

    def stop(self):
        pass

    def selection_made(self, selection):
        if len(selection) == 1:
            if selection[0]["type"] == SelectionType.command:
                parts = selection[0]["value"].split(" ")
                self._run_command(parts)
                self.q.put([Action.set_selection, []])
            elif selection[0]["type"] == SelectionType.entry:
                self.q.put([Action.copy_to_clipboard, selection[0]["value"]])
                self.q.put([Action.close])

            self._reload_ui_list()
            self._get_commands()
