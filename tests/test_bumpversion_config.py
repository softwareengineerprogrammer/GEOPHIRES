import re

from base_test_case import BaseTestCase


class BumpversionConfigTestCase(BaseTestCase):
    """
    Tests the regex pattern from the .bumpversion.cfg file.
    """

    # The pattern from the .bumpversion.cfg `parse` key
    parse_pattern = re.compile(
        r'(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)' r'(\-(?P<prerelease_label>[a-z]+)\.(?P<prerelease>\d+))?'
    )

    def test_parses_prerelease_version(self):
        """
        Verify that a version with a pre-release label is parsed correctly.
        """
        version_string = '3.9.30-alpha.0'
        match = self.parse_pattern.search(version_string)

        self.assertIsNotNone(match, 'The regex should match the pre-release version string.')

        parts = match.groupdict()
        self.assertEqual(parts['major'], '3')
        self.assertEqual(parts['minor'], '9')
        self.assertEqual(parts['patch'], '30')
        self.assertEqual(parts['prerelease_label'], 'alpha')
        self.assertEqual(parts['prerelease'], '0')

    def test_parses_release_version(self):
        """
        Verify that a standard release version is parsed correctly.
        """
        version_string = '3.9.30'
        match = self.parse_pattern.search(version_string)

        self.assertIsNotNone(match, 'The regex should match the standard release version string.')

        parts = match.groupdict()
        self.assertEqual(parts['major'], '3')
        self.assertEqual(parts['minor'], '9')
        self.assertEqual(parts['patch'], '30')
        self.assertIsNone(parts['prerelease_label'], 'The pre-release label should be None for a release version.')
        self.assertIsNone(parts['prerelease'], 'The pre-release number should be None for a release version.')

    def test_parses_rc_prerelease_version(self):
        """
        Verify that a version with a different pre-release label (rc) is parsed correctly.
        """
        version_string = '10.0.1-rc.12'
        match = self.parse_pattern.search(version_string)

        self.assertIsNotNone(match, 'The regex should match the rc pre-release version string.')

        parts = match.groupdict()
        self.assertEqual(parts['major'], '10')
        self.assertEqual(parts['minor'], '0')
        self.assertEqual(parts['patch'], '1')
        self.assertEqual(parts['prerelease_label'], 'rc')
        self.assertEqual(parts['prerelease'], '12')

    def test_does_not_match_invalid_string(self):
        """
        Verify that the regex does not match an invalid version string.
        """
        version_string = 'not-a-version'
        match = self.parse_pattern.search(version_string)
        self.assertIsNone(match, 'The regex should not match an invalid version string.')
