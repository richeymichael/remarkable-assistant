"""The application is a GUI for changing settings on the remarkable tablet"""
import os
from pathlib import Path
import sys
from threading import Thread
import uuid

import kivy
from kivy.app import App
from kivy.graphics import Color
from kivy.graphics import Rectangle
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
import paramiko

kivy.require('1.10.0')
LIMIT = 5

REMIND = '[b][color=ff0000] Restart tablet to see changes.[/color][/b]'
WARN = '[b][color=ff0000]NOT SAVED.[/color][/b] '

INITIALIZE = 'Attempting to connect to remarkable tablet'
NOT_CONNECTED = 'Failed to connect to remarkable tablet'
CONNECTED = 'Successfully connected to remarkable tablet'
LOCAL_FILE_SAVED = 'Settings saved locally'
REMOTE_FILE_SAVED = 'Settings saved to tablet' + REMIND
BE_SAFE = WARN + 'Times and password length must be greater than %d' % LIMIT
NO_LOCAL = WARN + 'Unable to find local settings'
EXITING = 'Exiting'

IDLE_KEY = 'IdleSuspendDelay'
SUSPEND_KEY = 'SuspendPowerOffDelay'
DEVPASS_KEY = 'DeveloperPassword'


class StatusLabel(Label):
    """Common label for statuses, helps w/ positioning"""

    def on_size(self, *args):
        """Needed this to get the status to the left"""
        self.canvas.before.clear()
        self.text_size = self.size
        with self.canvas.before:
            Color(1, 1, 1, 0.25)
            Rectangle(pos=self.pos, size=self.size)


class StatusLayout(AnchorLayout):
    """The status is going to be at the top left"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(StatusLayout, self).__init__(**kwargs)
        self.status = INITIALIZE
        self.anchor_x = 'left'
        self.status_label = StatusLabel(
            text=self.status,
            halign='left',
            valign='top',
            markup=True
        )
        self.add_widget(self.status_label)


class AppController(object):
    """The controller does the actual work of saving and fetching"""

    def __init__(self, config_layout, status_layout, **kwargs):
        """Initialize the class"""
        self.remotepath = '/home/root/.config/remarkable/xochitl.conf'
        self.status_layout = status_layout
        self.config_layout = config_layout
        file_uuid = str(uuid.uuid4())
        directory = './tmp/'
        if not os.path.exists(directory):
            os.makedirs(directory)
        self.temp_file = directory + file_uuid + '.bak'
        self.local_file = directory + file_uuid + '.new'
        self.get_config()

    def get_config(self, *args):
        """Always run this in the background"""
        self.status_layout.status_label.text = INITIALIZE
        Thread(target=self._get_config).start()

    def _get_config(self):
        """Get configuration file from the tablet and save it to uuid.bak"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                self.config_layout.ipaddress.text,
                port=int(self.config_layout.port.text),
                username=self.config_layout.username.text,
                password=self.config_layout.old_password.text,
                timeout=5
            )
            sftp = ssh.open_sftp()
            self.status_layout.status_label.text = CONNECTED
            sftp.get(self.remotepath, self.temp_file)
            file_handle = open(self.temp_file, 'r')
            for line in file_handle:
                if line.find(IDLE_KEY) == 0:
                    _, milliseconds = str.split(line, '=')
                    self.config_layout.idle.text = str(
                        int(milliseconds)/1000/60
                    )
                elif line.find(SUSPEND_KEY) == 0:
                    _, milliseconds = str.split(line, '=')
                    self.config_layout.suspend.text = str(
                        int(milliseconds)/1000/60
                    )
                elif line.find(DEVPASS_KEY) == 0:
                    _, password = str.split(line, '=')
                    self.config_layout.old_password.text = password.strip()
                    self.config_layout.password.text = password.strip()
        except paramiko.ssh_exception.AuthenticationException as conn_e:
            self.status_layout.status_label.text =  \
                NOT_CONNECTED + ': ' + conn_e.message
        except paramiko.ssh_exception.BadHostKeyException as conn_e:
            self.status_layout.status_label.text = \
                NOT_CONNECTED + ': ' + conn_e.message
        except paramiko.ssh_exception.SSHException as conn_e:
            self.status_layout.status_label.text = \
                NOT_CONNECTED + ': ' + conn_e.message
        except IOError as conn_e:
            self.status_layout.status_label.text = \
                NOT_CONNECTED + ': ' + conn_e.message

    def save_locally(self, *args):
        """Always run this in the background"""
        Thread(target=self._save_locally).start()

    def _save_locally(self):
        """Write out the file locally with the new vars to uuid.new"""
        if (self.config_layout.idle.text and
                self.config_layout.suspend.text and
                self.config_layout.idle.text.isdigit() and
                self.config_layout.suspend.text.isdigit() and
                len(self.config_layout.password.text) > LIMIT and
                int(self.config_layout.idle.text) > LIMIT and
                int(self.config_layout.suspend.text) > LIMIT):
            file_name = Path(self.temp_file)
            if file_name.is_file():
                file_input = open(self.temp_file, 'r')
                file_output = open(self.local_file, 'w')
                for line in file_input:
                    if line.find(IDLE_KEY) == 0:
                        line = IDLE_KEY + "=%d\n" % (
                            int(self.config_layout.idle.text)*1000*60
                        )
                    elif line.find(SUSPEND_KEY) == 0:
                        line = SUSPEND_KEY + "=%d\n" % (
                            int(self.config_layout.suspend.text)*1000*60
                        )
                    elif line.find(DEVPASS_KEY) == 0:
                        line = DEVPASS_KEY + "=%s\n" % (
                            self.config_layout.password.text.strip()
                        )
                    file_output.write(line)
                self.status_layout.status_label.text = LOCAL_FILE_SAVED
                return True
            else:
                self.status_layout.status_label.text = NOT_CONNECTED
                return False
        else:
            self.status_layout.status_label.text = BE_SAFE
            return False

    def save_to_tablet(self, *args):
        """Always run this in the background"""
        Thread(target=self._save_to_tablet).start()

    def _save_to_tablet(self):
        """Call save locally to write out uuid.new then sftp to tablet"""
        if self._save_locally() and self.config_layout.old_password:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(
                    self.config_layout.ipaddress.text,
                    port=int(self.config_layout.port.text),
                    username=self.config_layout.username.text,
                    password=self.config_layout.old_password.text,
                    timeout=5
                )
                sftp = ssh.open_sftp()
                self.status_layout.status_label.text = CONNECTED
                sftp.put(self.local_file, self.remotepath)
                self._get_config()
                self.status_layout.status_label.text = REMOTE_FILE_SAVED
            except paramiko.ssh_exception.AuthenticationException as conn_e:
                self.status_layout.status_label.text = \
                    NOT_CONNECTED + ': ' + conn_e.message
            except paramiko.ssh_exception.BadHostKeyException as conn_e:
                self.status_layout.status_label.text = \
                    NOT_CONNECTED + ': ' + conn_e.message
            except paramiko.ssh_exception.SSHException as conn_e:
                self.status_layout.status_label.text = \
                    NOT_CONNECTED + ': ' + conn_e.message
            except IOError as conn_e:
                self.status_layout.status_label.text = \
                    NOT_CONNECTED + ': ' + conn_e.message
        else:
            self.status_layout.status_label.text = NO_LOCAL

    def quit(self, obj):
        """Exit"""
        self.status_layout.status_label.text = EXITING
        file_name = Path(self.temp_file)
        if file_name.is_file():
            os.remove(self.temp_file)
        file_name = Path(self.local_file)
        if file_name.is_file():
            os.remove(self.local_file)
        sys.exit()


class ConfigLabel(Label):
    """Standarized the configuration labels"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(ConfigLabel, self).__init__(**kwargs)
        self.lines = self.text.count('\n') + 1
        self.font_size = (self.height - self.height*.2)/self.lines

    def on_size(self, *args):
        """Fix the fonts on resize"""
        self.lines = self.text.count('\n') + 1
        self.font_size = (self.height - self.height*.2)/self.lines


class ConfigInput(TextInput):
    """Standarized the configuration inputs"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(ConfigInput, self).__init__(**kwargs)
        self.multiline = False
        self.cursor_blink = True
        self.font_size = self.height - self.height*.2
        self.write_tab = False

    def on_size(self, *args):
        """Fix the fonts on resize"""
        self.font_size = self.height - self.height*.2


class ConfigLayout(GridLayout):
    """Two columns in a grid layout, label and input"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(ConfigLayout, self).__init__(**kwargs)
        self.cols = 2

        self.add_widget(ConfigLabel(text='IP Address'))
        self.ipaddress = ConfigInput(text='10.11.99.1')
        self.add_widget(self.ipaddress)

        self.add_widget(ConfigLabel(text='Port'))
        self.port = ConfigInput(text='22')
        self.add_widget(self.port)

        self.add_widget(ConfigLabel(text='Username'))
        self.username = ConfigInput(text='root')
        self.add_widget(self.username)

        self.add_widget(ConfigLabel(text='Old Password'))
        self.old_password = ConfigInput(password=True)
        self.add_widget(self.old_password)

        self.add_widget(ConfigLabel(text='New Password'))
        self.password = ConfigInput(password=True)
        self.add_widget(self.password)

        self.add_widget(
            Label(
                text='Idle Time Before Suspend\n(in minutes)',
                halign='center'
            )
        )
        self.idle = ConfigInput()
        self.add_widget(self.idle)

        self.add_widget(
            Label(
                text='Suspend Time Before PowerOff\n(in minutes)',
                halign='center'
            )
        )
        self.suspend = ConfigInput()
        self.add_widget(self.suspend)


class ButtonRowLayout(BoxLayout):
    """Buttons in a single row, pass in the controller to bind functions"""

    def __init__(self, app_controller, **kwargs):
        """Initialize the class"""
        super(ButtonRowLayout, self).__init__(**kwargs)
        self.app_controller = app_controller
        self.orientation = 'horizontal'

        self.recon_btn = Button(text='Attempt to reconnect')
        self.recon_btn.bind(on_press=self.app_controller.get_config)
        self.add_widget(self.recon_btn)

        self.save_btn = Button(text='Save settings to tablet')
        self.save_btn.bind(on_press=self.app_controller.save_to_tablet)
        self.add_widget(self.save_btn)

        # Used this for testing
        #self.save_local_btn = Button(text='Save settings locally')
        #self.save_local_btn.bind(on_press=self.app_controller.save_locally)
        #self.add_widget(self.save_local_btn)

        self.quit_btn = Button(text='Clean up and Quit')
        self.quit_btn.bind(on_press=self.app_controller.quit)
        self.add_widget(self.quit_btn)


class HomeScreen(BoxLayout):
    """Home screen is a vertical box layout"""

    def __init__(self, **kwargs):
        super(HomeScreen, self).__init__(**kwargs)
        self.orientation = 'vertical'

        self.status_layout = StatusLayout(size_hint=(1, .1))
        self.add_widget(self.status_layout)

        self.config_layout = ConfigLayout()
        self.add_widget(self.config_layout)

        self.app_controller = AppController(
            self.config_layout,
            self.status_layout
        )

        self.buttons = ButtonRowLayout(self.app_controller, size_hint=(1, .1))
        self.add_widget(self.buttons)


class MyApp(App):
    """The main application class"""

    def build(self):
        """Set title and build the HomeScreen (well a layout not a screen)"""
        self.title = "reMarkable Assistant"
        return HomeScreen()


if __name__ == '__main__':
    MyApp().run()
