"""Tests the main module of the CI service."""
# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import cStringIO
import subprocess
import os
import mock
import yaml

from daemon import main
import helpers


class MainTest(helpers.ExtendedTestCase):
  """Test main."""

  def setUp(self):
    helpers.patch(self, ['daemon.main.load_sanity_check_testcases',
                         'daemon.main.reset_and_run_testcase',
                         'daemon.clone_chromium.clone_chromium',
                         'daemon.main.update_auth_header',
                         'daemon.main.load_new_testcases'])
    self.setup_fake_filesystem()
    self.mock.load_sanity_check_testcases.return_value = [1, 2]
    self.mock.load_new_testcases.side_effect = [[3, 4], [5]]
    self.mock.reset_and_run_testcase.side_effect = [None, None, None, None,
                                                    SystemExit]

  def test_correct_calls(self):
    """Ensure the main method makes the correct calls to reproduce."""

    with self.assertRaises(SystemExit):
      main.main()

    self.assert_exact_calls(self.mock.load_sanity_check_testcases,
                            [mock.call()])
    self.assert_exact_calls(self.mock.clone_chromium, [mock.call()])
    self.assert_exact_calls(self.mock.load_new_testcases, [mock.call(None),
                                                           mock.call(3)])
    self.assert_exact_calls(self.mock.reset_and_run_testcase, [
        mock.call(1, 'sanity'), mock.call(2, 'sanity'),
        mock.call(3, 'continuous'), mock.call(4, 'continuous'),
        mock.call(5, 'continuous')])


class RunTestcaseTest(helpers.ExtendedTestCase):
  """Test the run_testcase method."""

  def setUp(self):
    helpers.patch(self, ['os.environ.copy',
                         'subprocess.Popen'])
    self.mock.Popen.return_value = mock.Mock(
        returncode=1, stdout=cStringIO.StringIO('Output\nChunks'))
    self.mock.copy.return_value = {'OS': 'ENVIRON'}

  def test_running_testcase(self):
    """Ensures testcases are run properly."""

    result = main.run_testcase(1234)
    home = os.path.expanduser('~')

    command = ('/bin/bash -c "export PATH=$PATH:%s/depot_tools && '
               '/python-daemon/clusterfuzz reproduce 1234"' % home)

    self.assertFalse(result)
    self.assert_exact_calls(self.mock.Popen, [mock.call(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.expanduser('~'),
        env={
            'OS': 'ENVIRON',
            'CF_QUIET': '1',
            'USER': 'CI',
            'CHROMIUM_SRC': main.CHROMIUM_SRC,
            'GOMA_GCE_SERVICE_ACCOUNT': 'default'},
        shell=True)])


class LoadSanityCheckTestcasesTest(helpers.ExtendedTestCase):
  """Tests the load_sanity_check_testcases method."""

  def setUp(self):
    self.setup_fake_filesystem()
    os.makedirs('/python-daemon/daemon')
    with open(main.SANITY_CHECKS, 'w') as f:
      f.write('testcases:\n')
      f.write('#ignore\n')
      f.write('        - 5899279404367872')

  def test_reading_testcases(self):
    """Ensures that testcases are read properly."""

    result = main.load_sanity_check_testcases()
    self.assertEqual(result, [5899279404367872])

class UpdateAuthHeadertest(helpers.ExtendedTestCase):
  """Tests the update_auth_header method."""

  def setUp(self):
    self.setup_fake_filesystem()
    helpers.patch(self, ['oauth2client.client.GoogleCredentials'])
    (self.mock.GoogleCredentials._get_implicit_credentials.return_value. #pylint: disable=protected-access
     get_access_token.return_value) = mock.Mock(access_token='Access token')

  def test_proper_update(self):
    """Ensures that the auth key is updated properly."""

    self.assertFalse(os.path.exists(main.CLUSTERFUZZ_DIR))
    main.update_auth_header()

    with open(main.AUTH_FILE_LOCATION, 'r') as f:
      self.assertEqual(f.read(), 'Bearer Access token')


class GetVersionTest(helpers.ExtendedTestCase):
  """Tests the get_version method."""

  def setUp(self):
    helpers.patch(self, ['subprocess.check_output'])
    self.result = yaml.dump({
        'chromium': ['chrome_job', 'libfuzzer_job'],
        'standalone': ['pdf_job', 'v8_job'],
        'Version': '0.2.2rc11'})
    self.mock.check_output.return_value = self.result

  def test_get_version(self):
    result = main.get_version()
    self.assertEqual(result, '0.2.2rc11')


class GetSupportedJobtypesTest(helpers.ExtendedTestCase):
  """Tests the get_supported_jobtypes method."""

  def setUp(self):
    helpers.patch(self, ['subprocess.check_output'])
    self.result = yaml.dump({
        'chromium': ['chrome_job', 'libfuzzer_job'],
        'standalone': ['pdf_job', 'v8_job'],
        'Version': '0.2.2rc11'})
    self.mock.check_output.return_value = self.result

  def test_get_supported_jobtypes(self):
    """Tests get_supported_jobtypes."""

    result = main.get_supported_jobtypes()
    correct = yaml.load(self.result)
    correct.pop('Version')
    self.assertEqual(result, correct)


class LoadNewTestcasesTest(helpers.ExtendedTestCase):
  """Tests the load_new_testcases method."""

  def setUp(self): #pylint: disable=missing-docstring
    self.setup_fake_filesystem()
    os.makedirs(os.path.expanduser('~/.clusterfuzz'))
    with open(main.AUTH_FILE_LOCATION, 'w') as f:
      f.write('Bearer xyzabc')

    helpers.patch(self, ['daemon.main.get_supported_jobtypes',
                         'requests.post',
                         'random.randint'])
    self.mock.randint.return_value = 6
    self.mock.get_supported_jobtypes.return_value = {'chromium': [
        'supported', 'support']}

  def test_no_latest_testcase(self):
    """Tests when no previous tests have been run."""

    self.mock.post.return_value.json.return_value = {
        'items': [{'jobType': 'supported',
                   'id': 12345},
                  {'jobType': 'unsupported',
                   'id': 98765},
                  {'jobType': 'support',
                   'id': 23456}]}

    result = main.load_new_testcases()
    self.assertEqual(result, [12345, 23456])
    self.assert_exact_calls(self.mock.post, [mock.call(
        'https://clusterfuzz.com/v2/testcases/load',
        headers={'Authorization': 'Bearer xyzabc'},
        json={'page': 1,
              'reproducible': 'yes'})])

  def test_partial_testcase_page(self):
    """Tests when the most recent testcase is still on page 1."""

    self.mock.post.return_value.json.return_value = {
        'items': [{'jobType': 'supported',
                   'id': 12345},
                  {'jobType': 'support',
                   'id': 34567},
                  {'jobType': 'unsupported',
                   'id': 98765},
                  {'jobType': 'support',
                   'id': 23456}]}

    result = main.load_new_testcases(34567)
    self.assertEqual(result, [12345])
    self.assert_exact_calls(self.mock.post, [mock.call(
        'https://clusterfuzz.com/v2/testcases/load',
        headers={'Authorization': 'Bearer xyzabc'},
        json={'page': 1,
              'reproducible': 'yes'})])

  def test_no_new_testcases(self):
    """Tests when there are no new testcases on the first page."""

    self.mock.post.return_value.json.side_effect = [
        {'items': [{'jobType': 'supported',
                    'id': 12345},
                   {'jobType': 'support',
                    'id': 34567},
                   {'jobType': 'unsupported',
                    'id': 98765},
                   {'jobType': 'support',
                    'id': 23456}]},
        {'items': [{'jobType': 'unsupported',
                    'id': 369},
                   {'jobType': 'supported',
                    'id': 13579}]}]

    result = main.load_new_testcases(12345)
    self.assertEqual(result, [13579])


class ResetAndRunTestcaseTest(helpers.ExtendedTestCase):
  """Tests the reset_and_run_testcase method."""

  def setUp(self): #pylint: disable=missing-docstring
    self.setup_fake_filesystem()
    os.makedirs(main.CHROMIUM_OUT)
    os.makedirs(main.CLUSTERFUZZ_DIR)

    helpers.patch(self, ['subprocess.check_call',
                         'daemon.stackdriver_logging.send_run',
                         'daemon.main.update_auth_header',
                         'daemon.main.get_version',
                         'daemon.main.run_testcase'])
    self.mock.get_version.return_value = '0.2.2rc11'
    self.mock.run_testcase.return_value = 'run_testcase'

  def test_reset_run_testcase(self):
    """Tests resetting a testcase properly prior to running."""

    self.assertTrue(os.path.exists(main.CHROMIUM_OUT))
    self.assertTrue(os.path.exists(main.CLUSTERFUZZ_DIR))
    main.reset_and_run_testcase(1234, 'sanity')
    self.assertFalse(os.path.exists(main.CHROMIUM_OUT))
    self.assertFalse(os.path.exists(main.CLUSTERFUZZ_DIR))
    self.assert_exact_calls(self.mock.update_auth_header, [
        mock.call()])
    self.assert_exact_calls(self.mock.send_run, [
        mock.call(1234, 'sanity', '0.2.2rc11', 'run_testcase')])
    environment = os.environ.copy()
    environment['PATH'] += ':%s' % main.DEPOT_TOOLS
    self.assert_exact_calls(self.mock.check_call, [
        mock.call('git checkout -f master', shell=True, cwd=main.CHROMIUM_SRC),
        mock.call('gclient sync', shell=True, cwd=main.CHROMIUM_SRC,
                  env=environment),
        mock.call('gclient runhooks', shell=True, cwd=main.CHROMIUM_SRC,
                  env=environment)])
