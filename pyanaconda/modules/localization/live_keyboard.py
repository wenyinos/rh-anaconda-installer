# Copyright (C) 2023 Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#

from abc import ABC, abstractmethod
import ast
import os
import shutil
from pyanaconda.core.util import execWithCaptureAsLiveUser
from pyanaconda.core.configuration.anaconda import conf

from pyanaconda.anaconda_loggers import get_module_logger
log = get_module_logger(__name__)

# Desktop environments of a live system we can read the keyboard configuration from.
LIVE_DESKTOP_GNOME = "gnome"
LIVE_DESKTOP_KDE = "kde"

# Processes identifying the desktop environment of the running live session.
DESKTOP_SHELL_PROCESSES = {
    "gnome-shell": LIVE_DESKTOP_GNOME,
    "plasmashell": LIVE_DESKTOP_KDE,
}


def _get_running_process_names():
    """Get the names of the running processes.

    :return: a list of the process names
    :rtype: list(str)
    """
    names = []

    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue

        try:
            with open(f"/proc/{pid}/comm") as f:
                names.append(f.read().strip())
        except OSError:
            # The process might have disappeared in the meantime.
            continue

    return names


def _get_live_desktop():
    """Detect the desktop environment of the running live system.

    The environment variables can't be used for the detection, because Anaconda
    is started via pkexec, which doesn't pass them on. Detect the desktop
    environment from the processes of the live session instead.

    :return: an identifier of the detected desktop environment or None
    :rtype: str or None
    """
    detected = set()

    for name in _get_running_process_names():
        desktop = DESKTOP_SHELL_PROCESSES.get(name)
        if desktop:
            detected.add(desktop)

    if len(detected) == 1:
        return detected.pop()

    if len(detected) > 1:
        log.debug("Multiple live desktop environments detected: %s", detected)

    return None


def get_live_keyboard_instance():
    """Return instance of a class based on the current running live system.

    :return: instance of a LiveSystemKeyboardBase based class for the current live environment
    :rtype: instance of class inherited from LiveSystemKeyboardBase class
    """
    if not conf.system.provides_liveuser:
        return None

    desktop = _get_live_desktop()

    if desktop == LIVE_DESKTOP_KDE:
        return KdePlasmaKeyboard()

    if desktop == LIVE_DESKTOP_GNOME:
        return GnomeShellKeyboard()

    # Keep the previous behaviour and assume GNOME Shell for live systems
    # we are not able to detect.
    log.debug("Unknown live desktop environment, assuming GNOME Shell.")
    return GnomeShellKeyboard()


class LiveSystemKeyboardBase(ABC):

    @abstractmethod
    def read_keyboard_layouts(self):
        """Read keyboard configuration from the current system.

        The configuration have to be returned in format which is understandable by us for the
        installation. That means localed will understand it.

        :return: a list of "layout (variant)" or "layout" layout specifications
        :rtype: list(str)
        """
        pass

    @staticmethod
    def _run_as_liveuser(argv):
        """Run the command in a system as liveuser user.

        :param list argv: list of arguments for the command.
        :return: output of the command
        :rtype: str
        """
        return execWithCaptureAsLiveUser(argv[0], argv[1:])


class GnomeShellKeyboard(LiveSystemKeyboardBase):

    def read_keyboard_layouts(self):
        """Read keyboard configuration from the current system.

        The configuration have to be returned in format which is understandable by us for the
        installation. That means localed will understand it.

        :return: a list of "layout (variant)" or "layout" layout specifications
        :rtype: list(str)
        """
        command_args = ["gsettings", "get", "org.gnome.desktop.input-sources", "sources"]
        sources = self._run_as_liveuser(command_args)
        result = self._convert_to_xkb_format(sources)
        return result

    def _convert_to_xkb_format(self, sources):
        # convert input "[('xkb', 'us'), ('xkb', 'cz+qwerty')]\n"
        # to a python list of '["us", "cz (qwerty)"]'
        try:
            sources = ast.literal_eval(sources.rstrip())
        except (SyntaxError, ValueError, TypeError):
            log.error("Gnome Shell keyboard configuration can't be obtained from source %s!",
                      sources)
            return []
        result = []

        for t in sources:
            # keep only 'xkb' type and ignore 'ibus' variants which can't be used in localed
            if t[0] == "xkb":
                layout = t[1]
                # change layout variant from 'cz+qwerty' to 'cz (qwerty)'
                if '+' in layout:
                    layout, variant = layout.split('+')
                    result.append(f"{layout} ({variant})")
                else:
                    result.append(layout)

        return result


class KdePlasmaKeyboard(LiveSystemKeyboardBase):
    """Read the keyboard configuration of a running Plasma session.

    The configuration is stored in the KDE keyboard configuration file
    (kxkbrc) in the home directory of the live user, where the layouts and
    their variants are kept in two parallel lists.
    """

    # Configurations of the KDE keyboard KCM.
    KDE_CONFIG_FILE = "kxkbrc"
    LAYOUTS_GROUP = "Layout"
    LAYOUTS_KEY = "LayoutList"
    VARIANTS_KEY = "VariantList"

    def read_keyboard_layouts(self):
        """Read keyboard configuration from the current system.

        The configuration have to be returned in format which is understandable by us for the
        installation. That means localed will understand it.

        :return: a list of "layout (variant)" or "layout" layout specifications
        :rtype: list(str)
        """
        layouts = self._read_kde_config_value(self.LAYOUTS_KEY)
        variants = self._read_kde_config_value(self.VARIANTS_KEY)
        result = self._convert_to_xkb_format(layouts, variants)
        return result

    def _read_kde_config_value(self, key):
        """Read a value from the KDE keyboard configuration file.

        :param str key: a name of the key to read
        :return: a comma separated list of the values or an empty string
        :rtype: str
        """
        command_args = [
            self._get_kreadconfig_command(),
            "--file", self.KDE_CONFIG_FILE,
            "--group", self.LAYOUTS_GROUP,
            "--key", key,
        ]

        try:
            return self._run_as_liveuser(command_args)
        except (OSError, RuntimeError) as e:
            log.error("KDE keyboard configuration can't be read: %s", e)
            return ""

    @staticmethod
    def _get_kreadconfig_command():
        """Get a command for reading the KDE configuration.

        Plasma 5 and Plasma 6 provide different tools.

        :return: a name of the command
        :rtype: str
        """
        for command in ("kreadconfig6", "kreadconfig5"):
            if shutil.which(command):
                return command

        # Fall back to the Plasma 6 tool. The command will fail with a
        # reasonable error message if it is not available.
        return "kreadconfig6"

    def _convert_to_xkb_format(self, layouts, variants):
        # convert the input "us,cz,de" and ",qwerty,"
        # to a python list of '["us", "cz (qwerty)", "de"]'
        if not layouts.strip():
            log.debug("No KDE keyboard configuration found.")
            return []

        layout_list = layouts.rstrip().split(",")
        variant_list = variants.rstrip().split(",")

        result = []

        for i, layout in enumerate(layout_list):
            layout = layout.strip()

            # Skip the empty entries of a malformed configuration.
            if not layout:
                continue

            variant = variant_list[i].strip() if i < len(variant_list) else ""

            # change layout variant from 'cz' + 'qwerty' to 'cz (qwerty)'
            if variant:
                result.append(f"{layout} ({variant})")
            else:
                result.append(layout)

        return result
