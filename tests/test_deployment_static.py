from django.test import Client, SimpleTestCase, override_settings


class ProductionStaticFilesTests(SimpleTestCase):
    # Tests use finders for speed; the image serves the collected STATIC_ROOT.
    @override_settings(DEBUG=False, WHITENOISE_USE_FINDERS=True)
    def test_base_template_static_assets_are_served_in_production_mode(self):
        client = Client()
        expected_types = {
            '/static/css/rubric.css': 'text/css',
            '/static/js/htmx.min.js': 'javascript',
        }

        for path, expected_type in expected_types.items():
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                content_type = response.headers.get('Content-Type', '')
                if expected_type == 'text/css':
                    self.assertTrue(content_type.startswith('text/css'), content_type)
                else:
                    self.assertIn('javascript', content_type.lower(), content_type)
                    self.assertTrue(b''.join(response.streaming_content))
