#
# Copyright (C) 2023  Red Hat, Inc.
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
import unittest
from unittest.mock import patch

from pyanaconda.modules.localization.live_keyboard import GnomeShellKeyboard, \
    KdePlasmaKeyboard, _get_live_desktop, get_live_keyboard_instance


class LiveSystemKeyboardTestCase(unittest.TestCase):
    @patch("pyanaconda.modules.localization.live_keyboard._get_live_desktop")
    @patch("pyanaconda.modules.localization.live_keyboard.conf")
    def test_get_live_keyboard_instance(self, mocked_conf, mocked_get_desktop):
        """Test get_live_keyboard_instance function."""
        mocked_conf.system.provides_liveuser = True

        # test the KDE Plasma desktop
        mocked_get_desktop.return_value = "kde"
        assert isinstance(get_live_keyboard_instance(), KdePlasmaKeyboard)

        # test the GNOME Shell desktop
        mocked_get_desktop.return_value = "gnome"
        assert isinstance(get_live_keyboard_instance(), GnomeShellKeyboard)

        # test an unknown desktop, GNOME Shell is assumed
        mocked_get_desktop.return_value = None
        assert isinstance(get_live_keyboard_instance(), GnomeShellKeyboard)

        # test a system without the live user
        mocked_conf.system.provides_liveuser = False
        assert get_live_keyboard_instance() is None

    @patch("pyanaconda.modules.localization.live_keyboard._get_running_process_names")
    def test_get_live_desktop(self, mocked_get_process_names):
        """Test the desktop environment detection."""
        # test the KDE Plasma desktop
        mocked_get_process_names.return_value = ["plasmashell", "bash", "kded6"]
        assert _get_live_desktop() == "kde"

        # test the GNOME Shell desktop
        mocked_get_process_names.return_value = ["gnome-shell", "bash", "gdm"]
        assert _get_live_desktop() == "gnome"

        # test an unknown desktop
        mocked_get_process_names.return_value = ["bash", "gdm"]
        assert _get_live_desktop() is None

        # test a system with multiple desktops detected
        mocked_get_process_names.return_value = ["plasmashell", "gnome-shell"]
        assert _get_live_desktop() is None

    def _check_gnome_shell_layouts_conversion(self, mocked_exec_with_capture, system_input, output):
        mocked_exec_with_capture.reset_mock()
        mocked_exec_with_capture.return_value = system_input

        gs = GnomeShellKeyboard()

        assert gs.read_keyboard_layouts() == output
        mocked_exec_with_capture.assert_called_once_with(
            "gsettings",
            ["get", "org.gnome.desktop.input-sources", "sources"]
            )

    @patch("pyanaconda.modules.localization.live_keyboard.execWithCaptureAsLiveUser")
    def test_gnome_shell_keyboard(self, mocked_exec_with_capture):
        """Test GnomeShellKeyboard live instance layouts."""
        # test one simple layout set
        self._check_gnome_shell_layouts_conversion(
            mocked_exec_with_capture=mocked_exec_with_capture,
            system_input=r"[('xkb', 'cz')]",
            output=["cz"]
        )

        # test one complex layout is set
        self._check_gnome_shell_layouts_conversion(
            mocked_exec_with_capture=mocked_exec_with_capture,
            system_input=r"[('xkb', 'cz+qwerty')]",
            output=["cz (qwerty)"]
        )

        # test multiple layouts are set
        self._check_gnome_shell_layouts_conversion(
            mocked_exec_with_capture=mocked_exec_with_capture,
            system_input=r"[('xkb', 'cz+qwerty'), ('xkb', 'us'), ('xkb', 'cz+dvorak-ucw')]",
            output=["cz (qwerty)", "us", "cz (dvorak-ucw)"]
        )

        # test layouts with ibus (ibus is ignored)
        self._check_gnome_shell_layouts_conversion(
            mocked_exec_with_capture=mocked_exec_with_capture,
            system_input=r"[('xkb', 'cz'), ('ibus', 'libpinyin')]",
            output=["cz"]
        )

        # test only ibus layout
        self._check_gnome_shell_layouts_conversion(
            mocked_exec_with_capture=mocked_exec_with_capture,
            system_input=r"[('ibus', 'libpinyin')]",
            output=[]
        )

        # test wrong input
        self._check_gnome_shell_layouts_conversion(
            mocked_exec_with_capture=mocked_exec_with_capture,
            system_input=r"wrong input",
            output=[]
        )

    def _check_kde_layouts_conversion(self, mocked_exec_with_capture,
                                      layouts, variants, output):
        mocked_exec_with_capture.reset_mock()

        def _mock_kreadconfig(command, argv, **kwargs):
            if "LayoutList" in argv:
                return layouts
            return variants

        mocked_exec_with_capture.side_effect = _mock_kreadconfig

        kde = KdePlasmaKeyboard()
        assert kde.read_keyboard_layouts() == output

    @patch("pyanaconda.modules.localization.live_keyboard.shutil.which")
    @patch("pyanaconda.modules.localization.live_keyboard.execWithCaptureAsLiveUser")
    def test_kde_plasma_keyboard(self, mocked_exec_with_capture, mocked_which):
        """Test KdePlasmaKeyboard live instance layouts."""
        mocked_which.return_value = "/usr/bin/kreadconfig6"

        # test one simple layout set
        self._check_kde_layouts_conversion(
            mocked_exec_with_capture=mocked_exec_with_capture,
            layouts="cz",
            variants="",
            output=["cz"]
        )

        # test one layout with a variant
        self._check_kde_layouts_conversion(
            mocked_exec_with_capture=mocked_exec_with_capture,
            layouts="cz",
            variants="qwerty",
            output=["cz (qwerty)"]
        )

        # test multiple layouts with variants
        self._check_kde_layouts_conversion(
            mocked_exec_with_capture=mocked_exec_with_capture,
            layouts="us,cz,de",
            variants=",qwerty,dvorak",
            output=["us", "cz (qwerty)", "de (dvorak)"]
        )

        # test a variant list shorter than the layout list
        self._check_kde_layouts_conversion(
            mocked_exec_with_capture=mocked_exec_with_capture,
            layouts="us,cz,de",
            variants=",qwerty",
            output=["us", "cz (qwerty)", "de"]
        )

        # test a missing layout list
        self._check_kde_layouts_conversion(
            mocked_exec_with_capture=mocked_exec_with_capture,
            layouts="",
            variants="",
            output=[]
        )

        # test a malformed layout list
        self._check_kde_layouts_conversion(
            mocked_exec_with_capture=mocked_exec_with_capture,
            layouts="us,,de",
            variants=",,",
            output=["us", "de"]
        )

    @patch("pyanaconda.modules.localization.live_keyboard.shutil.which")
    @patch("pyanaconda.modules.localization.live_keyboard.execWithCaptureAsLiveUser")
    def test_kde_kreadconfig_command(self, mocked_exec_with_capture, mocked_which):
        """Test the selection of the kreadconfig command."""
        mocked_exec_with_capture.side_effect = \
            lambda command, argv, **kwargs: "us" if "LayoutList" in argv else ""

        # test the Plasma 6 tool
        mocked_which.side_effect = lambda command: \
            "/usr/bin/kreadconfig6" if command == "kreadconfig6" else None
        assert KdePlasmaKeyboard().read_keyboard_layouts() == ["us"]

        # test the Plasma 5 tool
        mocked_which.side_effect = lambda command: \
            "/usr/bin/kreadconfig5" if command == "kreadconfig5" else None
        assert KdePlasmaKeyboard().read_keyboard_layouts() == ["us"]

        # test no tool available
        mocked_which.side_effect = lambda command: None
        assert KdePlasmaKeyboard().read_keyboard_layouts() == ["us"]

    @patch("pyanaconda.modules.localization.live_keyboard.shutil.which")
    @patch("pyanaconda.modules.localization.live_keyboard.execWithCaptureAsLiveUser")
    def test_kde_read_config_error(self, mocked_exec_with_capture, mocked_which):
        """Test a failure to read the KDE configuration."""
        mocked_which.return_value = "/usr/bin/kreadconfig6"
        mocked_exec_with_capture.side_effect = OSError("Cannot run the command.")

        assert KdePlasmaKeyboard().read_keyboard_layouts() == []
