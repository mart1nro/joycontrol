
from setuptools import setup, find_packages

setup(name='joycontrol',
      version='0.15',
      author='Robert Martin',
      author_email='martinro@informatik.hu-berlin.de',
      description='Emulate Nintendo Switch Controllers over Bluetooth',
      packages=find_packages(),
      package_data={'joycontrol': ['profile/sdp_record_hid.xml']},
      zip_safe=False,
      install_requires=[
          'hid', 'aioconsole', 'dbus-next'
      ]
)

