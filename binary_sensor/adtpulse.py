"""
This adds ADT Pulse sensor support to Home Assistant.
ADT Pulse integration that automatically exposes to Home Assistant all
sensors that are configured within Pulse.

To install, you must manually copy the adtpulse.py file into your
custom_components folder, for example on Mac:

   ~/.homeassistant/custom_components/sensor/adtpulse.py

Example configuration:

binary_sensor:
  - platform: adtpulse:
    username: your@email.com
    password: password


In the future, create an ADT Pulse alarm panel (alarm_control_panel/adtpulse.py)
"""
import logging
import re
import json
import requests

from requests import Session
from homeassistant.components.binary_sensor import BinarySensorDevice

_LOGGER = logging.getLogger(__name__)

ADTPULSE_DATA = 'adtpulse'

ADT_STATUS_MAP = {
    "Closed":    False,
    "Open":      True,
    "No Motion": False,
    "Motion":    True
}

ADT_DEVICE_CLASS_TAG_MAP = {
    "doorWindow": "door",
    "motion": "motion",
    "smoke": "smoke"
}

def setup_platform(hass, config, add_entities_callback, discovery_info=None):
    """Set up sensors for an ADT Pulse installation."""

#    scan_interval = 60
#    if scan_interval < datetime.timedelta(seconds=25):
#        _LOGGER.error(
#            'ADT Pulse disabled. Scan interval must be at least 25 secondsto prevent DDOSing ADT servers.')
#        return

    sensors = []
    session = requests.Session()

    # must login to ADT Pulse first
    # TODO: improve robustness by selecting the POST url from https://portal.adtpulse.com/ (to handle versioning)
    login_form_url = "https://portal.adtpulse.com/myhome/10.0.0-60/access/signin.jsp"
    form_data = {
        'username': config.get('username'),
        'password': config.get('password'),
        'sun': 'yes'
    }
    post = session.post(login_form_url, data=form_data)

    # FIXME: not sure what 10.0.0-60 is, other than perhaps a platform version?
    r = session.get('https://portal.adtpulse.com/myhome/10.0.0-60/ajax/homeViewDevAjax.jsp')
    response = json.loads(r.text)

    last_observed_timestamp = response['ts']

    sensors = []
    for desc in response['items']:
        # skip anything that is not a "sensor"
        if 'sensor' in desc['tags'].split(','):
            sensor = ADTBinarySensor(config, desc, last_observed_timestamp)
            sensors.append( sensor )
        else:
            _LOGGER.error("Currently does not support ADT sensor %s = '%s' (tags %S)", desc['id'], desc['name'], desc['tags'])

    add_entities_callback( sensors )

    hass.data[ADTPULSE_DATA] = {}
    hass.data[ADTPULSE_DATA]['sensors'] = []
    hass.data[ADTPULSE_DATA]['sensors'].extend(sensors)

# FIXME: be smart with updates, a new sensor might have appeared!!! (or disappeared)

class ADTBinarySensor(BinarySensorDevice):
    """A binary sensor implementation for ADT Pulse."""

    def __init__(self, config, desc, last_observed_timestamp):
        """Initialize the binary_sensor."""
        self._config = config
        self._desc = desc

        self._name = desc['name']
        self._id = desc['id']
        self._last_activity_timestamp = int( desc['state']['activityTs'] )
        self._last_observed_timestamp = last_observed_timestamp

        # extract the sensor status from the text description
        # e.g.:  Front Side Door - Closed\nLast Activity: 9/7 4:02 PM
        self._state = None
        match = re.search(r'-\s(.+)\n', desc['state']['statusTxt'])
        if match:
            status = match.group(1)
            if status in ADT_STATUS_MAP:
                self._state = ADT_STATUS_MAP[status]

        # NOTE: it may be better to determine state by using the "icon" to determine status
        #       devStatOpen -> open
        #       devStatOK   -> closed
        #       devStatTamper (for shock devices)

        # map the ADT Pulse device type tag to a binary_sensor class so the proper status
        # codes and icons are displayed. If device class is not specified, binary_sensor
        # default to a generic on/off sensor
        device_class = ADT_DEVICE_CLASS_TAG_MAP[ desc['tags'].split(',')[1] ]
        if device_class:
            self._device_class = device_class

        # since ADT Pulse does not separate the concept of a door or window sensor,
        # we try to autodetect window type sensors so the appropriate icon is displayed
        if self._device_class is 'door' :
            if 'Window' in self._name or 'window' in self._name:
                self._device_class = 'window'

        # TODO: just compare _timestamp to determine if an "event" occured?
        #(comparing state is not enough, since it could have flipped back to the same original state)

        _LOGGER.debug('Created new ADT %s sensor: %s', self._device_class, self._name)

    @property
    def name(self):
        """Return the name of the ADT sensor."""
        return self._name

    @property
    def should_poll(self):
        """Polling needed until periodic refresh of JSON data supported."""
        return True

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        return self._state

    @property
    def device_class(self):
        """Return the class of the binary sensor."""
        return self._device_class

"""
Example JSON response:

{
  "items": [
    {
      "state": {
        "icon": "devStatOK",
        "statusTxt": "Exterior Door - Closed\nLast Activity: 2/23 9:34 AM",
        "activityTs": 1519407240395
      },
      "id": "sensor-22",
      "devIndex": "11VER1",
      "name": "Exterior Door",
      "tags": "sensor,doorWindow"
    },
    { "state": {
        "icon": "devStatOK",
        "statusTxt": "Office Motion - No Motion\nLast Activity: Today 12:01 AM",
        "activityTs": 1537340469370
      },
      "id": "sensor-15",
      "devIndex": "10VER1",
      "name": "Office Motion",
      "tags": "sensor,motion"
    },
  ],
  "id": "hvwData",
  "ts": 1537352131080
}
"""