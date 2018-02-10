"""The application is a GUI for changing settings on the remarkable tablet"""
import json
import os
from os.path import expanduser
from pathlib import Path
import pickle
import requests
from shutil import copy2
import signal
import stat
import sys
from threading import Thread
import time
import uuid

import kivy

from kivy.app import App
from kivy import Config
from kivy.core.window import Window
from kivy.graphics import Color
from kivy.graphics import Rectangle
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import AsyncImage
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.tabbedpanel import TabbedPanel
from kivy.uix.tabbedpanel import TabbedPanelHeader
from kivy.uix.textinput import TextInput
import paramiko

Config.set('graphics', 'multisamples', '0')
kivy.require('1.10.0')
LIMIT = 5

REMIND = '[b][color=ff0000] Restart tablet to see changes.[/color][/b]'
WARN = '[b][color=ff0000]NOT SAVED.[/color][/b] '

INITIALIZE = 'Attempting to connect to remarkable tablet'
TIMES_NOT_SET = '[color=ff0000]On tablet select power settings and ' + \
    'toggle both settings off and on[/color]\nThen restart tablet.'
NOT_CONNECTED = 'Failed to connect to remarkable tablet'
CONNECTED = 'Successfully connected to remarkable tablet'
LOCAL_FILE_SAVED = 'Settings saved locally'
REMOTE_FILE_SAVED = 'Settings saved to tablet\n' + REMIND
BE_SAFE = WARN + '\nTimes and password length must be greater than %d' % LIMIT
NO_LOCAL = WARN + '\nUnable to find local settings'
EXITING = 'Exiting'
DOWNLOADING = 'Downloading'

IDLE_KEY = 'IdleSuspendDelay'
SUSPEND_KEY = 'SuspendPowerOffDelay'
DEVPASS_KEY = 'DeveloperPassword'

home = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    home = sys._MEIPASS
APP_HOME = home + '/remark-assist/'
if not os.path.exists(APP_HOME):
    os.makedirs(APP_HOME)
TMP_DIR = APP_HOME + 'tmp/'
TEMPLATE_DIR = APP_HOME + 'additional-templates/'
SPLASH_DIR = APP_HOME + 'splash/'
BACKUP_DIR = APP_HOME + 'myfiles/'

REMOTE_TEMPLATE_DIR = '/usr/share/remarkable/templates/'
REMOTE_SPLASH_DIR = '/usr/share/remarkable/'
REMOTE_DOC_DIR = '/home/root/.local/share/remarkable/xochitl'
UPLOAD_PATH = 'upload'

PICKLE_FILE = APP_HOME + 'config.pickle'
REMOTE_CONFIG_FILE = '/home/root/.config/remarkable/xochitl.conf'


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
    """The status is going to be at the bottom"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(StatusLayout, self).__init__(**kwargs)
        self.status = INITIALIZE
        self.anchor_x = 'left'
        self.status_label = StatusLabel(
            text=self.status,
            halign='center',
            markup=True
        )
        self.add_widget(self.status_label)


class AppController(object):
    """The controller does the actual work of saving and fetching"""
    RUNNING = 0
    UPDATING = 1
    STOPPING = 2

    def __init__(
            self,
            app_config_layout,
            tablet_config_layout,
            status_layout,
            my_files,
            friendly_my_files,
            **kwargs
    ):
        """Initialize the class"""
        self.status = self.RUNNING
        self.status_layout = status_layout
        self.app_config_layout = app_config_layout
        self.tablet_config_layout = tablet_config_layout
        self.friendly_my_files = friendly_my_files
        self.my_files = my_files
        file_uuid = str(uuid.uuid4())
        self.temp_file = TMP_DIR + file_uuid + '.bak'
        self.local_file = TMP_DIR + file_uuid + '.new'
        self.get_config()

    def reconnect(self, *args):
        """Attempt to get the config and files again"""
        self.get_config(*args)

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
                self.app_config_layout.ipaddress.text,
                port=int(self.app_config_layout.port.text),
                username=self.app_config_layout.username.text,
                password=self.app_config_layout.old_password.text,
                timeout=5
            )
            sftp = ssh.open_sftp()
            self.status_layout.status_label.text = CONNECTED
            sftp.get(REMOTE_CONFIG_FILE, self.temp_file)
            file_handle = open(self.temp_file, 'r')
            for line in file_handle:
                if line.find(IDLE_KEY) == 0:
                    _, milliseconds = str.split(line, '=')
                    self.tablet_config_layout.idle.text = str(
                        int(milliseconds)/1000/60
                    )
                elif line.find(SUSPEND_KEY) == 0:
                    _, milliseconds = str.split(line, '=')
                    self.tablet_config_layout.suspend.text = str(
                        int(milliseconds)/1000/60
                    )
                elif line.find(DEVPASS_KEY) == 0:
                    _, password = str.split(line, '=')
                    self.app_config_layout.old_password.text = password.strip()
                    self.tablet_config_layout.password.text = password.strip()
            if (not self.tablet_config_layout.idle.text or
                not self.tablet_config_layout.suspend.text):
                self.status_layout.status_label.text = TIMES_NOT_SET
        except paramiko.ssh_exception.AuthenticationException as conn_e:
            self.status_layout.status_label.text =  \
                NOT_CONNECTED + '\n' + str(conn_e)
        except paramiko.ssh_exception.BadHostKeyException as conn_e:
            self.status_layout.status_label.text = \
                NOT_CONNECTED + '\n' + str(conn_e)
        except paramiko.ssh_exception.SSHException as conn_e:
            self.status_layout.status_label.text = \
                NOT_CONNECTED + '\n' + str(conn_e)
        except IOError as conn_e:
            self.status_layout.status_label.text = \
                NOT_CONNECTED + '\n' + str(conn_e)

    def get_files(self, *args):
        """Always run this in the background"""
        signal.signal(signal.SIGALRM, self.signal_handler)
        signal.alarm(5)
        self.status = self.UPDATING
        self.status_layout.status_label.text = INITIALIZE
        Thread(target=self._get_files).start()

    def signal_handler(self, signum, frame):
        """Update the files in the view"""
        self.my_files.file_chooser._update_files()
        self.friendly_my_files.refresh_widget()
        if self.status == self.UPDATING:
            signal.signal(signal.SIGALRM, self.signal_handler)
            signal.alarm(5)
        else:
            signal.alarm(0)

    def _get_files(self, *args):
        """Pull down the files from the remarkable tablet"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                self.app_config_layout.ipaddress.text,
                port=int(self.app_config_layout.port.text),
                username=self.app_config_layout.username.text,
                password=self.app_config_layout.old_password.text,
                timeout=5
            )
            sftp = ssh.open_sftp()
            self._get_directory(sftp, REMOTE_DOC_DIR, BACKUP_DIR)
            self.status_layout.status_label.text = CONNECTED
            self.status = self.RUNNING
        except paramiko.ssh_exception.AuthenticationException as conn_e:
            self.status_layout.status_label.text =  \
                NOT_CONNECTED + '\n' + str(conn_e)
        except paramiko.ssh_exception.BadHostKeyException as conn_e:
            self.status_layout.status_label.text = \
                NOT_CONNECTED + '\n' + str(conn_e)
        except paramiko.ssh_exception.SSHException as conn_e:
            self.status_layout.status_label.text = \
                NOT_CONNECTED + '\n' + str(conn_e)
        except IOError as conn_e:
            self.status_layout.status_label.text = \
                NOT_CONNECTED + '\n' + str(conn_e)

    def _get_directory(self, sftp, remote_directory, local_directory):
        """Recurse through the directories"""
        remarkable_files = sftp.listdir_attr(remote_directory)
        for each in remarkable_files:
            if self.status == self.STOPPING:
                return
            self.status_layout.status_label.text = \
                DOWNLOADING + "\n" + each.filename
            if stat.S_ISDIR(each.st_mode):
                if not os.path.exists(local_directory + "/" + each.filename):
                    os.makedirs(local_directory + "/" + each.filename)
                self._get_directory(
                    sftp,
                    remote_directory + "/" + each.filename,
                    local_directory + "/" + each.filename
                )
            else:
                sftp.get(
                    remote_directory + "/" + each.filename,
                    local_directory + "/" + each.filename,
                )

    def save_locally(self, *args):
        """Always run this in the background"""
        Thread(target=self._save_locally).start()

    def _save_locally(self):
        """Write out the file locally with the new vars to uuid.new"""
        if (self.tablet_config_layout.idle.text and
                self.tablet_config_layout.suspend.text and
                self.tablet_config_layout.idle.text.isdigit() and
                self.tablet_config_layout.suspend.text.isdigit() and
                len(self.tablet_config_layout.password.text) > LIMIT and
                int(self.tablet_config_layout.idle.text) > LIMIT and
                int(self.tablet_config_layout.suspend.text) > LIMIT):
            file_name = Path(self.temp_file)
            if file_name.is_file():
                file_input = open(self.temp_file, 'r')
                file_output = open(self.local_file, 'w')
                for line in file_input:
                    if line.find(IDLE_KEY) == 0:
                        line = IDLE_KEY + "=%d\n" % (
                            int(self.tablet_config_layout.idle.text)*1000*60
                        )
                    elif line.find(SUSPEND_KEY) == 0:
                        line = SUSPEND_KEY + "=%d\n" % (
                            int(self.tablet_config_layout.suspend.text)*1000*60
                        )
                    elif line.find(DEVPASS_KEY) == 0:
                        line = DEVPASS_KEY + "=%s\n" % (
                            self.tablet_config_layout.password.text.strip()
                        )
                    file_output.write(line)
                save_pw = {
                    'password': self.tablet_config_layout.password.text.strip()
                }
                pickle_out = open(PICKLE_FILE, "wb")
                pickle.dump(save_pw, pickle_out)
                pickle_out.close()
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
        if self._save_locally() and self.app_config_layout.old_password:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(
                    self.app_config_layout.ipaddress.text,
                    port=int(self.app_config_layout.port.text),
                    username=self.app_config_layout.username.text,
                    password=self.app_config_layout.old_password.text,
                    timeout=5
                )
                sftp = ssh.open_sftp()
                self.status_layout.status_label.text = CONNECTED
                sftp.put(self.local_file, REMOTE_CONFIG_FILE)
                for item in os.listdir(TEMPLATE_DIR):
                    sftp.put(TEMPLATE_DIR + item, REMOTE_TEMPLATE_DIR + item)
                for item in os.listdir(SPLASH_DIR):
                    sftp.put(SPLASH_DIR + item, REMOTE_SPLASH_DIR + item)
                self.app_config_layout.old_password.text = \
                    self.tablet_config_layout.password.text.strip()
                save_pw = {
                    'password': self.app_config_layout.old_password.text.strip()
                }
                pickle_out = open(PICKLE_FILE, "wb")
                pickle.dump(save_pw, pickle_out)
                pickle_out.close()
                self._get_config()
                self.status_layout.status_label.text = REMOTE_FILE_SAVED
            except paramiko.ssh_exception.AuthenticationException as conn_e:
                self.status_layout.status_label.text = \
                    NOT_CONNECTED + '\n' + str(conn_e)
            except paramiko.ssh_exception.BadHostKeyException as conn_e:
                self.status_layout.status_label.text = \
                    NOT_CONNECTED + '\n' + str(conn_e)
            except paramiko.ssh_exception.SSHException as conn_e:
                self.status_layout.status_label.text = \
                    NOT_CONNECTED + '\n' + str(conn_e)
            except IOError as conn_e:
                self.status_layout.status_label.text = \
                    NOT_CONNECTED + '\n' + str(conn_e)
        else:
            self.status_layout.status_label.text = NO_LOCAL

    def quit(self, obj):
        """Exit"""
        self.status = self.STOPPING
        self.status_layout.status_label.text = EXITING
        file_name = Path(self.temp_file)
        if file_name.is_file():
            os.remove(self.temp_file)
        file_name = Path(self.local_file)
        if file_name.is_file():
            os.remove(self.local_file)
        save_pw = {
            'password': self.app_config_layout.old_password.text.strip()
        }
        pickle_out = open(PICKLE_FILE, "wb")
        pickle.dump(save_pw, pickle_out)
        pickle_out.close()
        sys.exit()


class ConfigLabel(Label):
    """Standarized the configuration labels"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(ConfigLabel, self).__init__(**kwargs)
        self.lines = self.text.count('\n') + 1


class ConfigInput(TextInput):
    """Standarized the configuration inputs"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(ConfigInput, self).__init__(**kwargs)
        self.multiline = False
        self.cursor_blink = True
        self.write_tab = False


class AppConfigLayout(GridLayout):
    """Two columns in a grid layout, label and input"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(AppConfigLayout, self).__init__(**kwargs)
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

        self.add_widget(ConfigLabel(text='Tablet Password'))
        self.old_password = ConfigInput(password=True)
        self.add_widget(self.old_password)

        if os.path.exists(PICKLE_FILE):
            pickle_in = open(PICKLE_FILE, "rb")
            save_data = pickle.load(pickle_in)
            pickle_in.close()
            self.old_password.text = save_data['password']


class TabletConfigLayout(GridLayout):
    """Two columns in a grid layout, label and input"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(TabletConfigLayout, self).__init__(**kwargs)
        self.cols = 2

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
                text='Suspend Time Before Power Off\n(in minutes)',
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

        self.recon_btn = Button(text='Reconnect')
        self.recon_btn.bind(on_press=self.app_controller.reconnect)
        self.add_widget(self.recon_btn)

        self.save_btn = Button(
            text='Push Settings, \nTemplates, and Screens',
            halign='center'
        )
        self.save_btn.bind(on_press=self.app_controller.save_to_tablet)
        self.add_widget(self.save_btn)

        self.back_btn = Button(
            text='Pull My Files',
            halign='center'
        )
        self.back_btn.bind(on_press=self.app_controller.get_files)
        self.add_widget(self.back_btn)

        self.quit_btn = Button(text='Quit')
        self.quit_btn.bind(on_press=self.app_controller.quit)
        self.add_widget(self.quit_btn)


class HomeScreen(BoxLayout):
    """Home screen will have tabs at top and status at bottom"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(HomeScreen, self).__init__(**kwargs)
        self.orientation = 'vertical'

        self.status_layout = StatusLayout(size_hint=(1, .1))
        self.tabs = TabbedPanel()
        app = App.get_running_app()
        app.tabs = self.tabs

        settings_header = TabbedPanelHeader(text='Assistant\nSettings')
        settings_header.content = AppSettings(status_layout=self.status_layout)
        self.tabs.add_widget(settings_header)
        self.tabs.default_tab = settings_header

        tab_settings_header = TabbedPanelHeader(text='Tablet\nSettings')
        tab_settings_header.content = TabletSettings(
            status_layout=self.status_layout
        )
        self.tabs.add_widget(tab_settings_header)

        templates_header = TabbedPanelHeader(text='Templates')
        templates_header.content = Templates()
        self.tabs.add_widget(templates_header)

        splash_header = TabbedPanelHeader(text='Splash\nScreens')
        splash_header.content = Splash()
        self.tabs.add_widget(splash_header)

        my_files_header = TabbedPanelHeader(text='My Files')
        my_files_header.content = MyFiles()
#        self.tabs.add_widget(my_files_header)

        friendly_files_header = TabbedPanelHeader(text='My Files')
        friendly_files_header.content = FriendlyMyFiles()
        self.tabs.add_widget(friendly_files_header)

        self.app_controller = AppController(
            settings_header.content.config_layout,
            tab_settings_header.content.config_layout,
            self.status_layout,
            my_files_header.content,
            friendly_files_header.content,
        )

        self.add_widget(self.tabs)

        self.buttons = ButtonRowLayout(self.app_controller, size_hint=(1, .1))
        self.add_widget(self.buttons)

        self.add_widget(self.status_layout)


class FriendlyMyFiles(ScrollView):
    """Your files but looking better"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(FriendlyMyFiles, self).__init__(**kwargs)
        self.size_hint=(1, 1)
        self.metadata = {}
        self.thumbs = {}
        self.layout = GridLayout(cols=4, spacing=10, size_hint_y=None)
        self.layout.bind(minimum_height=self.layout.setter('height'))
        self.get_data("")
        self.add_widget(self.layout)

    def refresh_widget(self, parent=""):
        """Refresh the screen"""
        self.clear_widgets()
        self.layout = GridLayout(cols=4, spacing=10, size_hint_y=None)
        self.layout.bind(minimum_height=self.layout.setter('height'))
        self.get_data(parent)
        self.add_widget(self.layout)

    def get_data(self, parent):
        """Get the data"""
        # Get metadata
        self.metadata = {}
        for item in os.listdir(BACKUP_DIR):
            if item.endswith('.metadata'):
                key, _ = item.split('.')
                with open(BACKUP_DIR + item, 'r') as metafile:
                    self.metadata[key] = json.load(metafile)

        # Order this stuff
        dirs = []
        files = []
        for key in self.metadata:
            self.metadata[key]['uuid'] = key
            if self.metadata[key]['type'] == 'CollectionType':
                dirs.append(self.metadata[key])
            else:
                files.append(self.metadata[key])
        sort_field = 'visibleName'
        ordered_dirs = sorted(dirs, key=lambda k: str.lower(str(k[sort_field])))
        ordered_files = sorted(files, key=lambda k: str.lower(str(k[sort_field])))
        ordered_keys = []
        for item in ordered_dirs:
            ordered_keys.append(item['uuid'])
        for item in ordered_files:
            ordered_keys.append(item['uuid'])

        # Get thumbnails
        self.thumbs = {}
        for key in self.metadata:
            if os.path.exists(BACKUP_DIR + key + '.thumbnails'):
                self.thumbs[key] = os.listdir(BACKUP_DIR + key + '.thumbnails')

                file_layout = BoxLayout(
                    orientation='vertical',
                    size_hint_y=None,
                    height=300
                )
                aimg = AsyncImage(
                    source = 'static/dir.png'
                )

        # Create a back if needed
        if parent:
            file_layout = BoxLayout(
                orientation='vertical',
                size_hint_y=None,
                height=300
            )
            aimg = AsyncImage(
                source = 'static/dir.png'
            )
            image_button = ImageButton(
                source=aimg.source,
                metadata={},
                key='',
                view=self
            )
            file_layout.add_widget(image_button)
            label = Label(
                text='Previous',
                halign='left',
                size_hint_y=None
            )
            file_layout.add_widget(label)
            self.layout.add_widget(file_layout)

        # Add files
        for key in ordered_keys:
            if self.metadata[key]['parent'] == parent:
                file_layout = BoxLayout(
                    orientation='vertical',
                    size_hint_y=None,
                    height=300
                )
                aimg = AsyncImage(
                    source = 'static/dir.png'
                )
                if key in self.thumbs:
                    aimg = AsyncImage(
                        source = BACKUP_DIR + key + '.thumbnails' + "/" + self.thumbs[key][0]
                    )
                image_button = ImageButton(
                    source=aimg.source,
                    metadata=self.metadata[key],
                    key=key,
                    view=self
                )
                file_layout.add_widget(image_button)
                filename = self.metadata[key]['visibleName']
                if len(filename) > 26:
                    newfilename = filename[:12] + '...' + filename[-11:]
                    filename = newfilename
                label = Label(
                    text=filename,
                    halign='left',
                    size_hint_y=None
                )
                file_layout.add_widget(label)
                self.layout.add_widget(file_layout)

    def on_dropfile(self, *args):
        """Copy a pdf to the web updload end point"""
        # this is dumb
        controller = self.parent.parent.parent.app_controller
        file_name = args[2]
        host = controller.app_config_layout.ipaddress.text
        url = 'http://' + host + '/' + UPLOAD_PATH
        with open(file_name, 'rb') as file_obj:
            response = requests.post(url, files={'file': file_obj})
            time.sleep(5)
            controller.get_files()
            controller.status_layout.status_label.text = response.text
        self.refresh_widget()


class ImageButton(ButtonBehavior, AsyncImage):
    """Images that act like Buttons"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        #super(ImageButton, self).__init__(**kwargs)
        super(ImageButton, self).__init__()
        if 'source' in kwargs:
            self.source = kwargs['source']
        if 'metadata' in kwargs:
            self.metadata = kwargs['metadata']
        if 'view' in kwargs:
            self.view = kwargs['view']
        if 'key' in kwargs:
            self.key = kwargs['key']

    def on_press(self):
        """Update the view"""
        if self.key:
            if self.metadata['type'] == 'CollectionType':
                self.view.refresh_widget(self.key)
        else:
            self.view.refresh_widget('')


class MyFiles(BoxLayout):
    """You can backup your files"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(MyFiles, self).__init__(**kwargs)
        self.orientation = 'vertical'
        self.file_chooser = FileChooserListView()
        self.file_chooser.rootpath = BACKUP_DIR
        self.file_chooser.path = BACKUP_DIR
        self.file_chooser.multiselect = True
        self.add_widget(self.file_chooser)

    def on_dropfile(self, *args):
        """Don't do anything if a file is dropped on this tab"""
        pass


class Splash(BoxLayout):
    """You can write over your splash screens"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(Splash, self).__init__(**kwargs)
        self.orientation = 'vertical'
        self.file_chooser = FileChooserListView()
        self.file_chooser.rootpath = SPLASH_DIR
        self.file_chooser.path = SPLASH_DIR
        self.file_chooser.multiselect = True
        self.add_widget(self.file_chooser)

    def on_dropfile(self, *args):
        """Copy the file to the local directory when a file is dropped here"""
        copy2(args[2], SPLASH_DIR)
        self.file_chooser._update_files()


class Templates(BoxLayout):
    """Only going to copy new templates out to the remarkable"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        super(Templates, self).__init__(**kwargs)
        self.orientation = 'vertical'
        self.file_chooser = FileChooserListView()
        self.file_chooser.rootpath = TEMPLATE_DIR
        self.file_chooser.path = TEMPLATE_DIR
        self.file_chooser.multiselect = True
        self.add_widget(self.file_chooser)

    def on_dropfile(self, *args):
        """Copy the file to the local directory when a file is dropped here"""
        copy2(args[2], TEMPLATE_DIR)
        self.file_chooser._update_files()


class TabletSettings(BoxLayout):
    """TabletSettings is a vertical box layout"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        #super(TabletSettings, self).__init__(**kwargs)
        super(TabletSettings, self).__init__()
        self.orientation = 'vertical'

        self.status_layout = kwargs['status_layout']

        self.config_layout = TabletConfigLayout()
        self.add_widget(self.config_layout)

    def on_dropfile(self, *args):
        """Don't do anything if a file is dropped on this tab"""
        pass


class AppSettings(BoxLayout):
    """AppSettings is a vertical box layout"""

    def __init__(self, **kwargs):
        """Initialize the class"""
        #super(AppSettings, self).__init__(**kwargs)
        super(AppSettings, self).__init__()
        self.orientation = 'vertical'

        self.status_layout = kwargs['status_layout']

        self.config_layout = AppConfigLayout()
        self.add_widget(self.config_layout)

    def on_dropfile(self, *args):
        """Don't do anything if a file is dropped on this tab"""
        pass


class MyApp(App):
    """The main application class"""

    def build(self):
        """Set title and build the HomeScreen (well a layout not a screen)"""
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
        if not os.path.exists(TMP_DIR):
            os.makedirs(TMP_DIR)
        if not os.path.exists(TEMPLATE_DIR):
            os.makedirs(TEMPLATE_DIR)
        if not os.path.exists(SPLASH_DIR):
            os.makedirs(SPLASH_DIR)
        self.title = "reMarkable Assistant"
        self.tabs = None
        Window.bind(on_dropfile=self._on_dropfile)
        return HomeScreen()

    def _on_dropfile(self, *args):
        """Call the the on_dropfile for the active tab's content"""
        Thread(
            target=self.tabs.current_tab.content.on_dropfile(self, *args)
        ).start()
        

if __name__ == '__main__':
    MyApp().run()
