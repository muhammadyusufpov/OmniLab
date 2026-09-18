import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
import smtplib
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from unittest.mock import patch

from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import (
    Client,
    RequestFactory,
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.urls import reverse

from config.environment import (
    DEFAULT_PUBLIC_ORIGIN,
    LOCAL_DEVELOPMENT_SECRET_KEY,
    get_allowed_hosts,
    get_django_secret_key,
    get_public_origin,
    is_production_environment,
    is_search_indexing_disabled,
)

from .email_delivery import (
    AUTHENTICATION_FAILURE,
    CONFIGURATION_FAILURE,
    CONNECTION_FAILURE,
    RECIPIENT_FAILURE,
    TIMEOUT_FAILURE,
    UNKNOWN_FAILURE,
    ContactEmailConfigurationError,
    ContactEmailDeliveryCountError,
    get_contact_email_failure_category,
    validate_contact_email_configuration,
)

from .views import (
    CHEMICAL_REACTION_VIRTUAL_LAB_PAGE,
    CHEMICAL_REACTION_VIRTUAL_LAB_VISIT_SOURCE,
    GUIDE_CHEMISTRY_PROFILES,
    GUIDE_LIBRARY_GROUPS,
    GUIDE_PAGE_REFERENCES,
    GUIDE_REACTION_FAMILY_BY_PAGE,
    GUIDE_RELATIONSHIP_DEFINITIONS,
    GUIDE_RELATIONSHIPS,
    GUIDE_SUPPORTED_REACTION_FAMILIES,
    GUIDED_EXPERIMENT_BOUNDARY,
    GUIDED_EXPERIMENT_PAGES,
    GUIDED_EXPERIMENT_SAFETY_WARNING,
    OBSERVATION_GUIDE_PAGES,
    OBSERVATION_GUIDE_SAFETY_WARNING,
    PRODUCT_FAQS,
    PRODUCTION_BASE_URL,
    PUBLIC_CANONICAL_URLS,
    REACTION_DEMOS,
    SODIUM_CHLORINE_DEMO,
    SODIUM_CHLORINE_DEMO_URL,
    SOCIAL_PREVIEW_ALT,
    SOCIAL_PREVIEW_URL,
    equation_uses_only_selected_reactants,
    increment_reaction_request_count,
    validate_complete_reaction_response,
)
from .reactions import (
    PRECIPITATE_COLORS,
    REACTION_MATRIX,
    SUPPORTED_CHEMICAL_IDS,
    get_reaction,
    supported_reaction_pairs,
)


def _increment_reaction_limit_in_process(
    database_path,
    client_digest,
    window_number,
    result_queue,
):
    result_queue.put(
        increment_reaction_request_count(
            client_digest,
            window_number,
            database_path=database_path,
        )
    )


class DjangoSecretConfigurationTests(SimpleTestCase):
    def test_configured_secret_is_used(self):
        configured_key = "a-protected-production-secret"

        self.assertEqual(
            get_django_secret_key(
                {
                    "RENDER": "true",
                    "OMNILAB_DJANGO_SECRET_KEY": configured_key,
                }
            ),
            configured_key,
        )

    def test_render_production_requires_secret(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "OMNILAB_DJANGO_SECRET_KEY must be set in production.",
        ):
            get_django_secret_key({"RENDER": "true"})

    def test_explicit_production_environment_requires_secret(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "OMNILAB_DJANGO_SECRET_KEY must be set in production.",
        ):
            get_django_secret_key({"OMNILAB_ENVIRONMENT": "production"})

    def test_local_development_uses_non_production_fallback(self):
        self.assertEqual(
            get_django_secret_key({}),
            LOCAL_DEVELOPMENT_SECRET_KEY,
        )


class DeploymentConfigurationTests(SimpleTestCase):
    def test_public_origin_defaults_to_current_production(self):
        self.assertEqual(get_public_origin({}), DEFAULT_PUBLIC_ORIGIN)

    def test_public_origin_accepts_one_https_origin(self):
        self.assertEqual(
            get_public_origin(
                {"OMNILAB_PUBLIC_ORIGIN": " https://lab.example.edu/ "}
            ),
            "https://lab.example.edu",
        )

    def test_public_origin_rejects_non_origin_values(self):
        invalid_values = (
            "http://lab.example.edu",
            "https://lab.example.edu/guides",
            "https://lab.example.edu?preview=true",
            "https://user:secret@lab.example.edu",
        )

        for value in invalid_values:
            with self.subTest(value=value), self.assertRaisesMessage(
                ImproperlyConfigured,
                "OMNILAB_PUBLIC_ORIGIN must be an HTTPS origin",
            ):
                get_public_origin({"OMNILAB_PUBLIC_ORIGIN": value})

    def test_public_origin_rejects_an_explicitly_empty_value(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "OMNILAB_PUBLIC_ORIGIN must be an HTTPS origin",
        ):
            get_public_origin({"OMNILAB_PUBLIC_ORIGIN": ""})

    def test_one_origin_setting_controls_all_absolute_discovery_urls(self):
        configured_origin = "https://chemistry.example.edu"
        environment = os.environ.copy()
        environment.update(
            {
                "DJANGO_SETTINGS_MODULE": "config.settings",
                "OMNILAB_NOINDEX": "true",
                "OMNILAB_PUBLIC_ORIGIN": configured_origin,
            }
        )
        probe = "\n".join(
            [
                "import json",
                "import django",
                "django.setup()",
                "from django.conf import settings",
                "from omnilab.views import (",
                "    PRODUCTION_BASE_URL, PUBLIC_CANONICAL_URLS,",
                "    REACTION_DEMOS, SOCIAL_PREVIEW_URL, robots_txt,",
                "    sitemap_xml,",
                ")",
                "print(json.dumps({",
                "    'origin': PRODUCTION_BASE_URL,",
                "    'canonicals': list(PUBLIC_CANONICAL_URLS.values()),",
                "    'demo_urls': [demo['url'] for demo in REACTION_DEMOS.values()],",
                "    'social_preview': SOCIAL_PREVIEW_URL,",
                "    'robots': robots_txt(None).content.decode(),",
                "    'sitemap': sitemap_xml(None).content.decode(),",
                "    'noindex': settings.OMNILAB_NOINDEX,",
                "}))",
            ]
        )

        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        discovery = json.loads(result.stdout)
        self.assertEqual(discovery["origin"], configured_origin)
        self.assertEqual(len(discovery["canonicals"]), 35)
        self.assertEqual(len(set(discovery["canonicals"])), 35)
        for url in (
            discovery["canonicals"]
            + discovery["demo_urls"]
            + [discovery["social_preview"]]
        ):
            with self.subTest(url=url):
                self.assertTrue(url.startswith(f"{configured_origin}/"))
        self.assertIn(
            f"Sitemap: {configured_origin}/sitemap.xml",
            discovery["robots"],
        )
        self.assertEqual(
            discovery["sitemap"].count(f"<loc>{configured_origin}/"),
            35,
        )
        self.assertTrue(discovery["noindex"])

    def test_allowed_hosts_can_be_supplied_for_another_host(self):
        self.assertEqual(
            get_allowed_hosts(
                {
                    "OMNILAB_ALLOWED_HOSTS": (
                        "lab.example.edu, staging.example.edu"
                    )
                }
            ),
            ["lab.example.edu", "staging.example.edu"],
        )

    def test_allowed_hosts_keep_the_current_render_default(self):
        self.assertIn(
            "omnilab-bk8q.onrender.com",
            get_allowed_hosts({}),
        )

    def test_noindex_switch_is_explicit_and_host_neutral(self):
        self.assertTrue(
            is_search_indexing_disabled({"OMNILAB_NOINDEX": " true "})
        )
        self.assertFalse(is_search_indexing_disabled({}))
        self.assertFalse(
            is_search_indexing_disabled({"OMNILAB_NOINDEX": "false"})
        )

    def test_health_check_is_dependency_free(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok\n")
        self.assertEqual(response["Content-Type"], "text/plain")

    def test_deployment_command_stops_when_secret_is_missing(self):
        environment = os.environ.copy()
        environment.pop("OMNILAB_DJANGO_SECRET_KEY", None)

        result = subprocess.run(
            ["sh", "deploy/omnilab.sh"],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 64)
        self.assertIn(
            "OMNILAB_DJANGO_SECRET_KEY must be set",
            result.stderr,
        )

    def test_deployment_command_rejects_invalid_process_setting(self):
        environment = os.environ.copy()
        environment.update(
            {
                "OMNILAB_DJANGO_SECRET_KEY": "test-only-secret",
                "WEB_CONCURRENCY": "two",
            }
        )

        result = subprocess.run(
            ["sh", "deploy/omnilab.sh"],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 64)
        self.assertIn(
            "WEB_CONCURRENCY must be a positive integer",
            result.stderr,
        )


class SearchIndexControlTests(SimpleTestCase):
    @override_settings(OMNILAB_NOINDEX=True)
    def test_noindex_header_applies_to_every_public_sitemap_route(self):
        sitemap_response = self.client.get("/sitemap.xml")
        root = ET.fromstring(sitemap_response.content)
        namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        public_paths = [
            node.text.removeprefix(PRODUCTION_BASE_URL) or "/"
            for node in root.findall("sitemap:url/sitemap:loc", namespace)
        ]

        self.assertEqual(len(public_paths), 35)
        for path in public_paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response["X-Robots-Tag"],
                    "noindex, nofollow",
                )

    @override_settings(OMNILAB_NOINDEX=False)
    def test_normal_responses_remain_indexable_with_production_canonical(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("X-Robots-Tag", response)
        self.assertContains(
            response,
            f'<link rel="canonical" href="{PUBLIC_CANONICAL_URLS["index"]}">',
            html=True,
        )


class ProductionTransportSecurityTests(SimpleTestCase):
    production_security_settings = {
        "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https"),
        "SECURE_SSL_REDIRECT": True,
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
        "SECURE_HSTS_SECONDS": 3600,
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": False,
        "SECURE_HSTS_PRELOAD": False,
    }

    def test_render_and_explicit_production_are_detected(self):
        self.assertTrue(is_production_environment({"RENDER": "true"}))
        self.assertTrue(
            is_production_environment(
                {"OMNILAB_ENVIRONMENT": "production"}
            )
        )
        self.assertFalse(is_production_environment({}))

    @override_settings(**production_security_settings)
    def test_forwarded_https_request_is_not_redirected(self):
        response = self.client.get(
            "/contact/",
            HTTP_HOST="omnilab-bk8q.onrender.com",
            HTTP_X_FORWARDED_PROTO="https",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Strict-Transport-Security"],
            "max-age=3600",
        )

    @override_settings(**production_security_settings)
    def test_plain_http_request_redirects_to_https(self):
        response = self.client.get(
            "/contact/",
            HTTP_HOST="omnilab-bk8q.onrender.com",
        )

        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            "https://omnilab-bk8q.onrender.com/contact/",
        )

    @override_settings(
        SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
        **production_security_settings,
    )
    def test_production_csrf_and_session_cookies_are_secure(self):
        response = self.client.get(
            "/contact/",
            HTTP_HOST="omnilab-bk8q.onrender.com",
            HTTP_X_FORWARDED_PROTO="https",
        )

        def use_session(request):
            request.session["security-check"] = True
            return HttpResponse()

        session_response = SessionMiddleware(use_session)(
            RequestFactory().get("/", secure=True)
        )

        self.assertTrue(response.cookies["csrftoken"]["secure"])
        self.assertTrue(
            session_response.cookies[settings.SESSION_COOKIE_NAME]["secure"]
        )

    def test_local_http_development_stays_enabled(self):
        self.assertFalse(settings.SECURE_SSL_REDIRECT)
        self.assertFalse(settings.SESSION_COOKIE_SECURE)
        self.assertFalse(settings.CSRF_COOKIE_SECURE)
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)
        self.assertIsNone(settings.SECURE_PROXY_SSL_HEADER)
        self.assertEqual(self.client.get("/contact/").status_code, 200)

    def test_production_deployment_check_is_clean(self):
        environment = os.environ.copy()
        environment.update(
            {
                "RENDER": "true",
                "OMNILAB_DJANGO_SECRET_KEY": (
                    "production-check-only-secret-with-enough-randomness-"
                    "6f57cf4d6ce349d0b7c8161b2308e4e9"
                ),
            }
        )
        result = subprocess.run(
            [sys.executable, "manage.py", "check", "--deploy"],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stdout + result.stderr,
        )
        output = result.stdout + result.stderr
        self.assertIn(
            "System check identified no issues",
            output,
        )
        self.assertNotIn("WARNINGS:", output)


class ContactEmailConfigurationTests(SimpleTestCase):
    @staticmethod
    def email_environment(**overrides):
        environment = os.environ.copy()
        environment.pop("RENDER", None)
        environment.pop("OMNILAB_ENVIRONMENT", None)
        environment.pop("OMNILAB_DJANGO_SECRET_KEY", None)
        environment.update(overrides)
        return environment

    def test_port_465_can_use_ssl_without_tls(self):
        result = subprocess.run(
            [
                sys.executable,
                "manage.py",
                "shell",
                "-c",
                (
                    "from django.conf import settings; "
                    "print(settings.EMAIL_PORT, "
                    "settings.EMAIL_USE_TLS, settings.EMAIL_USE_SSL)"
                ),
            ],
            cwd=settings.BASE_DIR,
            env=self.email_environment(
                OMNILAB_EMAIL_PORT="465",
                OMNILAB_EMAIL_USE_TLS="false",
                OMNILAB_EMAIL_USE_SSL="true",
            ),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stdout + result.stderr,
        )
        self.assertIn("465 False True", result.stdout)

    def test_tls_and_ssl_cannot_both_be_enabled(self):
        result = subprocess.run(
            [sys.executable, "manage.py", "check"],
            cwd=settings.BASE_DIR,
            env=self.email_environment(
                OMNILAB_EMAIL_USE_TLS="true",
                OMNILAB_EMAIL_USE_SSL="true",
            ),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn(
            (
                "OMNILAB_EMAIL_USE_TLS and OMNILAB_EMAIL_USE_SSL "
                "cannot both be true."
            ),
            output,
        )


class ContactEmailFailureEvidenceTests(SimpleTestCase):
    def test_each_failure_has_one_stable_privacy_safe_category(self):
        failures = (
            (ContactEmailConfigurationError(), CONFIGURATION_FAILURE),
            (
                smtplib.SMTPAuthenticationError(
                    535,
                    b"private provider detail",
                ),
                AUTHENTICATION_FAILURE,
            ),
            (
                ConnectionRefusedError("private SMTP host"),
                CONNECTION_FAILURE,
            ),
            (TimeoutError("private timeout detail"), TIMEOUT_FAILURE),
            (
                smtplib.SMTPRecipientsRefused(
                    {"private@example.com": (550, b"private refusal")}
                ),
                RECIPIENT_FAILURE,
            ),
            (ContactEmailDeliveryCountError(), UNKNOWN_FAILURE),
        )

        for error, expected_category in failures:
            with self.subTest(expected_category=expected_category):
                self.assertEqual(
                    get_contact_email_failure_category(error),
                    expected_category,
                )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="",
        EMAIL_PORT=587,
        EMAIL_HOST_USER="sender@example.com",
        EMAIL_HOST_PASSWORD="private password",
        DEFAULT_FROM_EMAIL="sender@example.com",
        OMNILAB_CONTACT_TO_EMAIL="founder@example.com",
    )
    def test_incomplete_smtp_configuration_fails_before_delivery(self):
        with self.assertRaises(ContactEmailConfigurationError):
            validate_contact_email_configuration()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.com",
        EMAIL_PORT=587,
        EMAIL_HOST_USER="sender@example.com",
        EMAIL_HOST_PASSWORD="private password",
        DEFAULT_FROM_EMAIL="sender@example.com",
        OMNILAB_CONTACT_TO_EMAIL="founder@example.com",
    )
    def test_complete_smtp_configuration_can_attempt_delivery(self):
        self.assertIsNone(validate_contact_email_configuration())


class FaqPageTests(TestCase):
    def setUp(self):
        self.response = self.client.get("/faq/")

    def test_faq_content_is_visible_on_dedicated_page(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertEqual(len(PRODUCT_FAQS), 6)

        for faq in PRODUCT_FAQS:
            self.assertContains(self.response, faq["question"])
            self.assertContains(self.response, faq["answer"])

    def test_contact_help_faq_links_to_the_contact_form(self):
        contact_help_faq = next(
            faq
            for faq in PRODUCT_FAQS
            if faq["question"] == "How can I contact and get help?"
        )

        self.assertEqual(contact_help_faq["link_url"], "/contact/")
        rendered_answer = (
            contact_help_faq["answer_before_link"]
            + contact_help_faq["answer_link_text"]
            + contact_help_faq["answer_after_link"]
        )
        self.assertEqual(rendered_answer, contact_help_faq["answer"])
        self.assertContains(
            self.response,
            (
                "<p>"
                "Use the "
                '<a class="faq-answer-link" href="/contact/">Contact page</a>'
                " to ask a question, report something that isn't working, or "
                "suggest an improvement. Submit only the details needed to "
                "understand your request, and OmniLab will show whether your "
                "message was sent."
                "</p>"
            ),
            html=True,
        )

    def test_faq_schema_matches_visible_content(self):
        html = self.response.content.decode()
        schema_match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>',
            html,
            re.DOTALL,
        )

        self.assertIsNotNone(schema_match)
        schema = json.loads(schema_match.group(1))
        self.assertEqual(schema["@context"], "https://schema.org")
        self.assertEqual(schema["@type"], "FAQPage")
        self.assertEqual(len(schema["mainEntity"]), len(PRODUCT_FAQS))

        for faq, entity in zip(PRODUCT_FAQS, schema["mainEntity"]):
            self.assertEqual(entity["@type"], "Question")
            self.assertEqual(entity["name"], faq["question"])
            self.assertEqual(entity["acceptedAnswer"]["@type"], "Answer")
            self.assertEqual(entity["acceptedAnswer"]["text"], faq["answer"])

    def test_homepage_has_no_faq_content_or_schema(self):
        response = self.client.get("/")
        html = response.content.decode()
        schemas = [
            json.loads(match)
            for match in re.findall(
                r'<script type="application/ld\+json">(.*?)</script>',
                html,
                re.DOTALL,
            )
        ]

        self.assertNotContains(response, 'class="faq-list"')
        for faq in PRODUCT_FAQS:
            self.assertNotContains(response, faq["question"])
            self.assertNotContains(response, faq["answer"])
        self.assertNotIn("FAQPage", {schema.get("@type") for schema in schemas})

    def test_footer_links_to_faq_from_homepage(self):
        response = self.client.get("/")

        self.assertContains(
            response,
            '<a href="/faq/">FAQ</a>',
            html=True,
        )

    def test_supported_inputs_faq_states_thirty_four_reaction_pairs(self):
        supported_inputs_faq = next(
            faq
            for faq in PRODUCT_FAQS
            if faq["question"] == "Which chemicals and equipment can I use?"
        )
        self.assertIn("supports 34 reaction pairs", supported_inputs_faq["answer"])
        self.assertContains(self.response, supported_inputs_faq["answer"])

        html = self.response.content.decode()
        schema_match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(schema_match)
        schema = json.loads(schema_match.group(1))
        supported_inputs_entity = next(
            entity
            for entity in schema["mainEntity"]
            if entity["name"] == supported_inputs_faq["question"]
        )
        self.assertEqual(
            supported_inputs_entity["acceptedAnswer"]["text"],
            supported_inputs_faq["answer"],
        )

    def test_mobile_faq_action_stays_inside_its_content_column(self):
        css = (settings.BASE_DIR / "static/css/style.css").read_text()

        self.assertRegex(
            css,
            r"\.faq-primary\s*\{[^}]*box-sizing:\s*border-box;",
        )


class HomepageResponsiveLayoutTests(SimpleTestCase):
    def setUp(self):
        self.css = (settings.BASE_DIR / "static/css/style.css").read_text()

    def test_toolbar_stays_aligned_and_contained(self):
        self.assertRegex(
            self.css,
            r"\.excalidraw-floating-toolbar\s*\{[^}]*"
            r"width:\s*max-content;[^}]*"
            r"max-width:\s*calc\(100vw - 32px\);[^}]*"
            r"box-sizing:\s*border-box;",
        )
        self.assertRegex(
            self.css,
            re.compile(
                r"@media\s*\(max-width:\s*991\.98px\)\s*\{.*?"
                r"\.excalidraw-floating-toolbar\s*\{[^}]*"
                r"left:\s*0;[^}]*"
                r"transform:\s*none;[^}]*"
                r"margin:\s*10px auto;",
                re.DOTALL,
            ),
        )
        self.assertRegex(
            self.css,
            re.compile(
                r"@media\s*\(min-width:\s*1200px\)\s*\{.*?"
                r"\.home-page \.excalidraw-floating-toolbar\s*\{[^}]*"
                r"left:\s*calc\(33\.333333% \+ 192px\);",
                re.DOTALL,
            ),
        )

    def test_homepage_first_experiment_entry_stays_visible_on_mobile(self):
        homepage = self.client.get("/")

        self.assertContains(
            homepage,
            '<a class="home-first-experiment-entry" href="/first-experiment/">',
        )
        self.assertEqual(
            homepage.content.decode().count("Run your first experiment"),
            1,
        )
        self.assertRegex(
            self.css,
            re.compile(
                r"\.home-first-experiment-entry\s*\{[^}]*"
                r"min-height:\s*44px;[^}]*"
                r"display:\s*inline-flex;",
                re.DOTALL,
            ),
        )
        self.assertIn(".home-first-experiment-entry:focus-visible", self.css)
        self.assertRegex(
            self.css,
            re.compile(
                r"@media\s*\(max-width:\s*991\.98px\)\s*\{.*?"
                r"\.home-page \.app-title-card:not\("
                r"\.app-title-card--guided\)\s*\{[^}]*"
                r"display:\s*block;[^}]*\}.*?"
                r"\.home-page \.app-title-card:not\("
                r"\.app-title-card--guided\) > :not\("
                r"\.home-first-experiment-entry\)\s*\{\s*display:\s*none;",
                re.DOTALL,
            ),
        )

    def test_guided_demo_keeps_its_mobile_instruction_card(self):
        homepage = self.client.get("/")
        guided_demo = self.client.get("/demo/sodium-chlorine/")

        self.assertContains(homepage, '<header class="app-title-card">')
        self.assertContains(
            guided_demo,
            '<header class="app-title-card app-title-card--guided">',
        )


class GuideLibraryPageTests(TestCase):
    def setUp(self):
        self.response = self.client.get("/guides/")
        self.html = self.response.content.decode()
        self.guides = [
            guide
            for group in GUIDE_LIBRARY_GROUPS
            for guide in group["guides"]
        ]

    def test_library_groups_all_twenty_eight_guides_once(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertContains(
            self.response,
            "Twenty-eight questions · One connected library",
        )
        self.assertEqual(len(self.guides), 28)
        self.assertEqual(self.html.count('class="guide-index-link"'), 28)

        guide_hrefs = re.findall(
            r'<a class="guide-index-link" href="([^"]+)">',
            self.html,
        )
        expected_hrefs = [
            reverse(guide["route_name"]) for guide in self.guides
        ]
        self.assertEqual(guide_hrefs, expected_hrefs)
        self.assertEqual(len(set(guide_hrefs)), 28)

        for group in GUIDE_LIBRARY_GROUPS:
            with self.subTest(group=group["label"]):
                self.assertContains(self.response, group["label"])
        for guide in self.guides:
            with self.subTest(guide=guide["title"]):
                self.assertContains(self.response, guide["title"])
                self.assertContains(self.response, guide["summary"])

    def test_library_keeps_one_grid_heading_without_duplicate_intro(self):
        self.assertEqual(
            self.html.count(
                '<h2 id="library-heading">'
                "Start where your chemistry question starts"
                "</h2>"
            ),
            1,
        )
        self.assertNotContains(
            self.response,
            "The twenty-five guides are grouped by the job they help you do",
        )

    def test_library_description_names_twenty_eight_free_no_account_guides(self):
        description = self.response.context["page_description"]

        self.assertIn("28 free, no-account chemistry guides", description)
        self.assertLessEqual(len(description), 160)
        self.assertContains(
            self.response,
            f'<meta name="description" content="{description}">',
            html=True,
        )

    def test_all_twenty_eight_guides_have_distinct_titles_and_descriptions(self):
        self.assertEqual(len(GUIDE_PAGE_REFERENCES), 28)
        self.assertEqual(
            len(
                {
                    guide["page_title"]
                    for guide in GUIDE_PAGE_REFERENCES.values()
                }
            ),
            28,
        )
        self.assertEqual(
            len(
                {
                    guide["description"]
                    for guide in GUIDE_PAGE_REFERENCES.values()
                }
            ),
            28,
        )

        for guide in GUIDE_PAGE_REFERENCES.values():
            with self.subTest(guide=guide["title"]):
                response = self.client.get(reverse(guide["route_name"]))

                self.assertContains(
                    response,
                    f'<title>{guide["page_title"]}</title>',
                    html=True,
                )
                self.assertContains(
                    response,
                    (
                        '<meta name="description" '
                        f'content="{guide["description"]}">'
                    ),
                    html=True,
                )

    def test_every_guide_has_a_small_explicit_relationship_set(self):
        self.assertEqual(
            set(GUIDE_RELATIONSHIPS),
            set(GUIDE_PAGE_REFERENCES),
        )
        for guide_key, relationships in GUIDE_RELATIONSHIPS.items():
            with self.subTest(guide_key=guide_key):
                self.assertIn(len(relationships), (2, 3))
                related_keys = [
                    related_key for related_key, _reason in relationships
                ]
                self.assertEqual(len(related_keys), len(set(related_keys)))
                self.assertNotIn(guide_key, related_keys)
                self.assertTrue(
                    set(related_keys).issubset(GUIDE_PAGE_REFERENCES)
                )

    def test_guide_map_covers_all_pages_and_supported_reaction_families(self):
        virtual_lab_key = CHEMICAL_REACTION_VIRTUAL_LAB_PAGE["canonical_key"]
        reaction_matrix_family_ids = {
            "+".join(sorted(pair)) for pair in REACTION_MATRIX
        }

        self.assertEqual(
            set(GUIDE_REACTION_FAMILY_BY_PAGE),
            set(GUIDE_PAGE_REFERENCES) - {virtual_lab_key},
        )
        self.assertEqual(len(set(GUIDE_REACTION_FAMILY_BY_PAGE.values())), 25)
        self.assertTrue(
            set(GUIDE_REACTION_FAMILY_BY_PAGE.values()).issubset(
                reaction_matrix_family_ids
            )
        )
        self.assertEqual(
            GUIDE_SUPPORTED_REACTION_FAMILIES[virtual_lab_key],
            frozenset(GUIDE_REACTION_FAMILY_BY_PAGE.values()),
        )
        self.assertEqual(
            set(GUIDE_SUPPORTED_REACTION_FAMILIES),
            set(GUIDE_PAGE_REFERENCES),
        )

    def test_every_relationship_has_explicit_chemistry_evidence(self):
        self.assertEqual(
            set(GUIDE_RELATIONSHIP_DEFINITIONS),
            set(GUIDE_PAGE_REFERENCES),
        )
        self.assertEqual(
            set(GUIDE_CHEMISTRY_PROFILES),
            set(GUIDE_PAGE_REFERENCES),
        )

        for guide_key, relationships in GUIDE_RELATIONSHIP_DEFINITIONS.items():
            for relationship in relationships:
                self.assertEqual(
                    len(relationship),
                    4,
                    f"Malformed relationship for {guide_key}: {relationship!r}",
                )
                (
                    related_key,
                    _reason,
                    evidence_kind,
                    evidence_value,
                ) = relationship
                with self.subTest(
                    guide_key=guide_key,
                    related_key=related_key,
                    evidence_kind=evidence_kind,
                    evidence_value=evidence_value,
                ):
                    if evidence_kind == "supported_reaction_family":
                        self.assertIn(
                            evidence_value,
                            GUIDE_SUPPORTED_REACTION_FAMILIES[guide_key]
                            & GUIDE_SUPPORTED_REACTION_FAMILIES[related_key],
                        )
                    elif evidence_kind == "shared_substance":
                        self.assertIn(
                            evidence_value,
                            GUIDE_CHEMISTRY_PROFILES[guide_key]["substances"]
                            & GUIDE_CHEMISTRY_PROFILES[related_key]["substances"],
                        )
                    elif evidence_kind == "shared_reaction_pattern":
                        self.assertIn(
                            evidence_value,
                            GUIDE_CHEMISTRY_PROFILES[guide_key][
                                "reaction_patterns"
                            ]
                            & GUIDE_CHEMISTRY_PROFILES[related_key][
                                "reaction_patterns"
                            ],
                        )
                    else:
                        self.fail(f"Unknown relationship evidence: {evidence_kind}")

    def test_all_guide_templates_use_the_shared_related_guides_partial(self):
        template_dir = Path(settings.BASE_DIR) / "templates"
        partial_include = 'include "partials/related_guides.html"'

        for template_name in (
            "chemical_reaction_virtual_lab.html",
            "guided_experiment.html",
            "observation_guide.html",
        ):
            with self.subTest(template_name=template_name):
                template = (template_dir / template_name).read_text()
                self.assertEqual(template.count(partial_include), 1)
                self.assertNotIn("{% for related_guide in related_guides %}", template)

    def test_every_guide_navigation_destination_returns_success(self):
        prepared_demo_routes = {
            "chemical_reaction_virtual_lab": "sodium_chlorine_demo",
            **{
                guide["canonical_key"]: "sodium_chlorine_demo"
                for guide in GUIDED_EXPERIMENT_PAGES.values()
            },
            **{
                guide["canonical_key"]: guide["demo_route_name"]
                for guide in OBSERVATION_GUIDE_PAGES.values()
            },
        }
        visit_sources = {
            "chemical_reaction_virtual_lab": (
                CHEMICAL_REACTION_VIRTUAL_LAB_VISIT_SOURCE
            ),
            **{
                guide["canonical_key"]: guide["visit_source"]
                for guide in GUIDED_EXPERIMENT_PAGES.values()
            },
            **{
                guide["canonical_key"]: guide["visit_source"]
                for guide in OBSERVATION_GUIDE_PAGES.values()
            },
        }

        self.assertEqual(
            set(prepared_demo_routes),
            set(GUIDE_PAGE_REFERENCES),
        )

        for guide_key, guide in GUIDE_PAGE_REFERENCES.items():
            with self.subTest(guide_key=guide_key):
                response = self.client.get(reverse(guide["route_name"]))
                self.assertEqual(response.status_code, 200)

                demo_path = reverse(prepared_demo_routes[guide_key])
                prepared_href = (
                    f'{demo_path}?source={visit_sources[guide_key]}'
                )
                self.assertContains(
                    response,
                    f'href="{prepared_href}"',
                )
                self.assertEqual(
                    self.client.get(prepared_href).status_code,
                    200,
                )

                for related_key, _reason in GUIDE_RELATIONSHIPS[guide_key]:
                    related_path = reverse(
                        GUIDE_PAGE_REFERENCES[related_key]["route_name"]
                    )
                    self.assertContains(
                        response,
                        f'href="{related_path}"',
                    )
                    self.assertEqual(
                        self.client.get(related_path).status_code,
                        200,
                    )

    def test_virtual_lab_guide_uses_shared_metadata_and_related_links(self):
        response = self.client.get(
            reverse(CHEMICAL_REACTION_VIRTUAL_LAB_PAGE["route_name"])
        )
        html = response.content.decode()
        related_block = html.split(
            'class="guide-related reaction-lab-related"', 1
        )[1].split("</nav>", 1)[0]

        self.assertEqual(related_block.count("<a href="), 3)
        for related_key, reason in GUIDE_RELATIONSHIPS[
            "chemical_reaction_virtual_lab"
        ]:
            related_guide = GUIDE_PAGE_REFERENCES[related_key]
            self.assertIn(
                f'href="{reverse(related_guide["route_name"])}"',
                related_block,
            )
            self.assertIn(related_guide["title"], related_block)
            self.assertIn(reason, related_block)

    def test_library_keeps_one_primary_lab_action(self):
        self.assertEqual(self.html.count('class="guide-primary"'), 1)
        self.assertContains(
            self.response,
            '<a class="guide-primary" href="/#lab-workspace">',
            html=False,
        )
        self.assertNotIn(
            'class="guide-primary"',
            "\n".join(
                re.findall(
                    r'<a class="guide-index-link".*?</a>',
                    self.html,
                    re.DOTALL,
                )
            ),
        )

    def test_mobile_primary_action_stays_inside_its_content_column(self):
        css = (settings.BASE_DIR / "static/css/style.css").read_text()

        self.assertRegex(
            css,
            r"\.guide-primary\s*\{[^}]*max-width:\s*100%;"
            r"[^}]*box-sizing:\s*border-box;",
        )

    def test_library_has_collection_schema_for_the_visible_guides(self):
        schema_match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>',
            self.html,
            re.DOTALL,
        )

        self.assertIsNotNone(schema_match)
        schema = json.loads(schema_match.group(1))
        self.assertEqual(schema["@type"], "CollectionPage")
        self.assertEqual(schema["url"], PUBLIC_CANONICAL_URLS["guides"])
        item_list = schema["mainEntity"]
        self.assertEqual(item_list["@type"], "ItemList")
        self.assertEqual(item_list["numberOfItems"], 28)
        self.assertEqual(len(item_list["itemListElement"]), 28)

        for position, (guide, item) in enumerate(
            zip(self.guides, item_list["itemListElement"]),
            start=1,
        ):
            with self.subTest(guide=guide["title"]):
                self.assertEqual(item["@type"], "ListItem")
                self.assertEqual(item["position"], position)
                self.assertEqual(item["item"]["@type"], "LearningResource")
                self.assertEqual(item["item"]["name"], guide["title"])
                self.assertEqual(
                    item["item"]["url"],
                    PUBLIC_CANONICAL_URLS[guide["canonical_key"]],
                )

    def test_library_has_canonical_sitemap_and_sitewide_footer_discovery(self):
        self.assertContains(
            self.response,
            (
                '<link rel="canonical" '
                f'href="{PUBLIC_CANONICAL_URLS["guides"]}">'
            ),
            html=True,
        )
        sitemap = self.client.get("/sitemap.xml")
        root = ET.fromstring(sitemap.content)
        namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = [
            node.text
            for node in root.findall("sitemap:url/sitemap:loc", namespace)
        ]
        self.assertEqual(
            locations.count(PUBLIC_CANONICAL_URLS["guides"]),
            1,
        )
        for path in ("/", "/faq/", "/guides/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(
                    response,
                    '<a href="/guides/">Guides</a>',
                    html=True,
                )


class HomepageGuideLibraryTests(TestCase):
    def test_homepage_uses_one_compact_route_to_the_complete_library(self):
        response = self.client.get("/")
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Twenty-eight chemistry guides")
        self.assertContains(response, "Explore the chemistry guide library")
        self.assertContains(response, "Explore all 28 chemistry guides")
        self.assertEqual(
            html.count('class="guide-library-overview-link"'),
            1,
        )
        self.assertContains(
            response,
            (
                '<a class="guide-library-overview-link" '
                'href="/guides/">'
            ),
            html=False,
        )
        self.assertNotContains(response, 'class="guide-library-link"')

        for guide in GUIDE_PAGE_REFERENCES.values():
            with self.subTest(guide=guide["title"]):
                guide_path = reverse(guide["route_name"])
                self.assertNotIn(f'href="{guide_path}"', html)

    def test_guide_library_route_is_secondary_to_the_analyze_action(self):
        response = self.client.get("/")
        html = response.content.decode()

        self.assertEqual(html.count('class="btn action-btn-primary'), 1)
        self.assertNotContains(response, 'class="guide-primary"')
        self.assertNotContains(response, 'class="btn guide-library-link"')

    def test_demo_stays_focused_on_the_prepared_reaction(self):
        response = self.client.get("/demo/sodium-chlorine/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Twenty-eight chemistry guides")
        self.assertNotContains(response, 'class="guide-library-link"')


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="omnilab-bk8q@mail.tin.computer",
    OMNILAB_CONTACT_TO_EMAIL="founder@example.com",
)
class ContactFormTests(TestCase):
    def tearDown(self):
        cache.clear()

    def test_contact_page_has_in_page_form_and_no_footer_mailto(self):
        response = self.client.get("/contact/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h1 id=\"contact-heading\">What can we help with?</h1>", html=True)
        self.assertContains(response, '<form class="contact-form" method="post"', html=False)
        self.assertContains(response, '<label for="id_name">Name</label>', html=True)
        self.assertContains(response, '<label for="id_email">Email</label>', html=True)
        self.assertContains(response, "Subject <span>(optional)</span>", html=True)
        self.assertContains(response, '<label for="id_message">Message</label>', html=True)
        self.assertContains(response, '<button type="submit">Submit', html=False)
        self.assertNotContains(
            response,
            'href="mailto:omnilab-bk8q@mail.tin.computer">Contact</a>',
        )
        self.assertNotContains(response, "What were you trying to predict?")

    def test_reaction_feedback_prefills_only_the_fixed_questions_and_source(self):
        response = self.client.get(
            "/contact/?source=reaction_feedback"
            "&result=NaCl&title=Private+page&next=https://example.com"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<h1 id="contact-heading">What were you trying to do?</h1>',
            html=True,
        )
        self.assertContains(
            response,
            'name="source" value="reaction_feedback"',
            html=False,
        )
        self.assertContains(response, "What were you trying to predict?")
        self.assertContains(response, "What do you plan to do next?")
        self.assertContains(
            response,
            '<label class="contact-session-option" for="id_session_interest">',
            html=False,
        )
        self.assertContains(
            response,
            "Yes, I'd be open to a short, unrecorded conversation.",
        )
        self.assertContains(
            response,
            "It doesn't schedule anything.",
        )
        self.assertNotContains(response, '<label for="id_subject">', html=False)
        for private_value in (
            "NaCl",
            "Private page",
            "https://example.com",
        ):
            with self.subTest(private_value=private_value):
                self.assertNotContains(response, private_value)

    def test_arbitrary_contact_source_does_not_prefill_feedback(self):
        response = self.client.get(
            "/contact/?source=guide_reaction&message=Injected"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<h1 id="contact-heading">What can we help with?</h1>',
            html=True,
        )
        self.assertNotContains(response, 'name="session_interest"', html=False)
        self.assertNotContains(response, "What were you trying to predict?")
        self.assertNotContains(response, "Injected")

    def test_feedback_analytics_are_production_only(self):
        production_response = self.client.get(
            "/contact/?source=reaction_feedback",
            HTTP_HOST="omnilab-bk8q.onrender.com",
        )
        local_response = self.client.get(
            "/contact/?source=reaction_feedback",
            HTTP_HOST="testserver",
        )

        for marker in (
            "posthog.init(",
            "https://us.i.posthog.com",
            "phc_qHnj5nPFZW9VcTqT82jtjsEHkQk6PTh8g65RrqUBSST7",
        ):
            with self.subTest(marker=marker):
                self.assertContains(production_response, marker, count=1)
                self.assertNotContains(local_response, marker)

        for response in (production_response, local_response):
            self.assertContains(
                response,
                '<script type="module" src="/static/js/root/feedback.js"></script>',
                html=True,
            )
            self.assertContains(
                response,
                'data-feedback-event="reaction_feedback_viewed"',
                html=False,
            )

    def test_ordinary_contact_route_remains_uninstrumented(self):
        response = self.client.get(
            "/contact/",
            HTTP_HOST="omnilab-bk8q.onrender.com",
        )

        self.assertNotContains(response, "posthog.init(")
        self.assertNotContains(response, "/static/js/root/feedback.js")
        self.assertNotContains(response, "data-feedback-event")

    def test_contact_success_acknowledges_acceptance_without_delivery_claim(self):
        response = self.client.get("/contact/?sent=1")

        self.assertContains(
            response,
            "<strong>Message accepted.</strong>",
            html=True,
        )
        self.assertContains(
            response,
            "Your note was accepted for delivery.",
        )
        self.assertNotContains(response, "Message sent.")

    def test_feedback_success_uses_accepted_event(self):
        response = self.client.get(
            "/contact/?sent=1&source=reaction_feedback"
        )

        self.assertContains(
            response,
            'data-feedback-event="reaction_feedback_accepted"',
            html=False,
        )
        self.assertNotContains(response, "reaction_feedback_viewed")

    def test_invalid_feedback_uses_validation_failed_event(self):
        response = self.client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "not-an-email",
                "message": "",
                "source": "reaction_feedback",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'data-feedback-event="reaction_feedback_validation_failed"',
            html=False,
        )

    @override_settings(OMNILAB_CONTACT_RATE_LIMIT_REQUESTS=1)
    def test_rate_limited_feedback_uses_rate_limited_event(self):
        data = {
            "name": "Amina Student",
            "email": "amina@example.edu",
            "message": "I was comparing this result with my notes.",
            "source": "reaction_feedback",
        }

        first = self.client.post("/contact/", data)
        second = self.client.post("/contact/", data)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 429)
        self.assertContains(
            second,
            'data-feedback-event="reaction_feedback_rate_limited"',
            html=False,
            status_code=429,
        )

    @patch("omnilab.views.EmailMessage.send", side_effect=OSError("SMTP detail"))
    def test_failed_feedback_delivery_uses_delivery_failed_event(self, send):
        with self.assertLogs("omnilab.contact", level="ERROR") as logs:
            response = self.client.post(
                "/contact/",
                {
                    "name": "Amina Student",
                    "email": "amina@example.edu",
                    "message": "I was comparing this result with my notes.",
                    "source": "reaction_feedback",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'data-feedback-event="reaction_feedback_delivery_failed"',
            html=False,
        )
        self.assertEqual(
            logs.output,
            [
                "ERROR:omnilab.contact:"
                "contact_email_delivery_failed category=connection"
            ],
        )
        self.assertNotIn("SMTP detail", logs.output[0])
        self.assertNotIn("amina@example.edu", logs.output[0])
        send.assert_called_once_with(fail_silently=False)

    @patch("omnilab.views.EmailMessage.send", return_value=0)
    def test_zero_delivery_count_cannot_show_feedback_success(self, send):
        response = self.client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "amina@example.edu",
                "message": "I was comparing this result with my notes.",
                "source": "reaction_feedback",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Feedback sent.")
        self.assertContains(
            response,
            "Your message couldn&#x27;t be sent right now.",
        )
        self.assertContains(
            response,
            'data-feedback-event="reaction_feedback_delivery_failed"',
            html=False,
        )
        send.assert_called_once_with(fail_silently=False)

    def test_feedback_events_have_no_custom_properties(self):
        source = "\n".join(
            (
                (
                    settings.BASE_DIR
                    / "static/ts/interactions/feedback.ts"
                ).read_text(),
                (
                    settings.BASE_DIR / "static/ts/root/feedback.ts"
                ).read_text(),
            )
        )
        events = re.findall(r"'(reaction_feedback_[a-z_]+)'", source)

        self.assertEqual(
            events,
            [
                "reaction_feedback_opened",
                "reaction_feedback_prompt_viewed",
                "reaction_feedback_viewed",
                "reaction_feedback_accepted",
                "reaction_feedback_validation_failed",
                "reaction_feedback_rate_limited",
                "reaction_feedback_delivery_failed",
            ],
        )
        self.assertIn("capture('reaction_feedback_prompt_viewed');", source)
        self.assertIn("capture('reaction_feedback_opened');", source)
        self.assertIn("capture(feedbackEvent);", source)
        self.assertNotIn("capture('reaction_feedback_prompt_viewed',", source)
        self.assertNotIn("capture('reaction_feedback_opened',", source)
        self.assertNotIn("capture(feedbackEvent,", source)

    def test_contact_fields_stay_inside_the_form_card(self):
        css = (settings.BASE_DIR / "static/css/style.css").read_text()

        self.assertRegex(
            css,
            (
                r"\.contact-field input,\s*"
                r"\.contact-field textarea\s*\{[^}]*"
                r"box-sizing:\s*border-box;"
            ),
        )

    def test_mobile_contact_heading_stacks_without_crowding(self):
        css = (settings.BASE_DIR / "static/css/style.css").read_text()

        mobile_rules = css.split("@media (max-width: 560px)", 1)[1]
        self.assertRegex(
            mobile_rules,
            (
                r"\.contact-form-heading\s*\{[^}]*"
                r"flex-direction:\s*column;"
            ),
        )

    def test_valid_contact_message_is_delivered_to_configured_mailbox(self):
        response = self.client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "amina@example.edu",
                "subject": "Reaction question",
                "message": "Could you add another acid-base example?",
            },
        )

        self.assertRedirects(
            response,
            "/contact/?sent=1",
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["founder@example.com"])
        self.assertEqual(message.reply_to, ["amina@example.edu"])
        self.assertEqual(
            message.subject,
            "OmniLab contact: Reaction question",
        )
        self.assertIn("Name: Amina Student", message.body)
        self.assertIn("Could you add another acid-base example?", message.body)
        self.assertNotIn("amina@example.edu", response["Location"])

    def test_subject_is_optional_and_uses_neutral_email_subject(self):
        response = self.client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "amina@example.edu",
                "subject": "",
                "message": "I have a question about the lab.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            mail.outbox[0].subject,
            "OmniLab contact: New website message",
        )

    def test_reaction_feedback_opt_in_uses_student_session_subject(self):
        response = self.client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "amina@example.edu",
                "subject": "Tampered subject",
                "message": (
                    "What were you trying to predict?\n\n"
                    "An acid-base reaction.\n\n"
                    "What do you plan to do next?\n\n"
                    "Compare it with my notes."
                ),
                "source": "reaction_feedback",
                "session_interest": "on",
            },
        )

        self.assertRedirects(
            response,
            "/contact/?sent=1&source=reaction_feedback",
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(
            message.subject,
            "OmniLab contact: Student session interest",
        )
        self.assertIn("Source: Reaction feedback", message.body)
        self.assertIn("Student session interest: Yes", message.body)
        self.assertNotIn("Tampered subject", message.subject)
        self.assertNotIn("Tampered subject", message.body)

    def test_reaction_feedback_without_opt_in_records_no_interest(self):
        response = self.client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "amina@example.edu",
                "message": (
                    "What were you trying to predict?\n\n"
                    "An acid-base reaction.\n\n"
                    "What do you plan to do next?\n\n"
                    "Compare it with my notes."
                ),
                "source": "reaction_feedback",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            mail.outbox[0].subject,
            "OmniLab contact: Learner feedback",
        )
        self.assertIn(
            "Student session interest: No",
            mail.outbox[0].body,
        )

    def test_general_contact_never_forwards_session_interest(self):
        response = self.client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "amina@example.edu",
                "message": "Question",
                "session_interest": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("Student session interest:", mail.outbox[0].body)

    def test_arbitrary_posted_source_is_not_forwarded(self):
        response = self.client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "amina@example.edu",
                "message": "Question",
                "source": "guide_reaction",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/contact/?sent=1")
        self.assertNotIn("Source:", mail.outbox[0].body)

    def test_invalid_contact_message_stays_on_page_with_field_values(self):
        response = self.client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "not-an-email",
                "subject": "Question",
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email address.")
        self.assertContains(response, "Enter a message.")
        self.assertContains(response, 'value="Amina Student"', html=False)
        self.assertEqual(len(mail.outbox), 0)

    @patch("omnilab.views.EmailMessage.send", side_effect=OSError("SMTP detail"))
    def test_delivery_failure_stays_on_page_without_exposing_details(self, send):
        response = self.client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "amina@example.edu",
                "subject": "Question",
                "message": "I have a question about the lab.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Your message couldn&#x27;t be sent right now.",
        )
        self.assertNotContains(response, "SMTP detail")
        self.assertContains(
            response,
            'value="Amina Student"',
            html=False,
        )
        send.assert_called_once_with(fail_silently=False)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.invalid",
        EMAIL_PORT=587,
        EMAIL_HOST_USER="sender@example.com",
        EMAIL_HOST_PASSWORD="private password",
        DEFAULT_FROM_EMAIL="sender@example.com",
        OMNILAB_CONTACT_TO_EMAIL="founder@example.com",
        EMAIL_USE_TLS=False,
    )
    @patch("django.core.mail.backends.smtp.EmailBackend.connection_class")
    def test_delivery_timeout_uses_bounded_setting_and_safe_error(
        self,
        connection_class,
    ):
        connection_class.side_effect = TimeoutError("SMTP timed out")

        response = self.client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "amina@example.edu",
                "subject": "Question",
                "message": "I have a question about the lab.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Your message couldn&#x27;t be sent right now.",
        )
        self.assertNotContains(response, "SMTP timed out")
        self.assertLessEqual(settings.EMAIL_TIMEOUT, 8)
        connection_class.assert_called_once()
        self.assertEqual(
            connection_class.call_args.kwargs["timeout"],
            settings.EMAIL_TIMEOUT,
        )

    def test_honeypot_submission_is_not_delivered(self):
        response = self.client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "amina@example.edu",
                "message": "Automated submission",
                "website": "https://example.com",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(OMNILAB_CONTACT_RATE_LIMIT_REQUESTS=1)
    def test_contact_rate_limit_blocks_second_valid_submission(self):
        data = {
            "name": "Amina Student",
            "email": "amina@example.edu",
            "message": "I have a question about the lab.",
        }

        first = self.client.post("/contact/", data)
        second = self.client.post("/contact/", data)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 429)
        self.assertContains(
            second,
            "Too many messages were sent from this network.",
            status_code=429,
        )
        self.assertIn("Retry-After", second)
        self.assertEqual(len(mail.outbox), 1)

    def test_contact_form_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        rejected = csrf_client.post(
            "/contact/",
            {
                "name": "Amina Student",
                "email": "amina@example.edu",
                "message": "Question",
            },
        )

        self.assertEqual(rejected.status_code, 403)

        page = csrf_client.get("/contact/")
        token = page.cookies["csrftoken"].value
        accepted = csrf_client.post(
            "/contact/",
            {
                "csrfmiddlewaretoken": token,
                "name": "Amina Student",
                "email": "amina@example.edu",
                "message": "Question",
            },
        )
        self.assertEqual(accepted.status_code, 302)


class SearchDiscoveryTests(TestCase):
    def test_indexnow_key_file_is_available_at_the_origin_root(self):
        key = (
            "a94d996aed18be0932540221541260e95651607e49a7bbc46deecc9dbe788b35"
        )

        response = self.client.get(f"/{key}.txt")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        self.assertEqual(response.content.decode(), f"{key}\n")

    def test_chemical_reaction_virtual_lab_page_is_complete_and_discoverable(self):
        response = self.client.get("/guides/chemical-reaction-virtual-lab/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<h1 id=\"reaction-lab-heading\">Try a chemical reaction in a virtual lab</h1>",
            html=True,
        )
        self.assertContains(response, "34 supported reaction pairs")
        self.assertContains(response, "38 available substances")
        self.assertContains(response, "Try Sodium + Chlorine")
        self.assertContains(
            response,
            (
                '<link rel="canonical" href="'
                f'{PUBLIC_CANONICAL_URLS["chemical_reaction_virtual_lab"]}">'
            ),
            html=True,
        )

    def test_chemical_reaction_virtual_lab_has_one_attributed_primary_path(self):
        response = self.client.get(
            "/guides/chemical-reaction-virtual-lab/"
            "?source=arbitrary-private-value"
        )
        html = response.content.decode()

        self.assertEqual(html.count('class="guide-primary"'), 1)
        self.assertEqual(
            html.count(
                'href="/demo/sodium-chlorine/'
                f'?source={CHEMICAL_REACTION_VIRTUAL_LAB_VISIT_SOURCE}"'
            ),
            1,
        )
        self.assertContains(response, "Open the full reaction lab")
        self.assertContains(
            response,
            "window.guideVisitSource = "
            f'"{CHEMICAL_REACTION_VIRTUAL_LAB_VISIT_SOURCE}";',
        )
        self.assertContains(
            response,
            '<script type="module" src="/static/js/root/guide.js"></script>',
            html=True,
        )
        self.assertNotContains(response, "arbitrary-private-value")

    def test_chemical_reaction_virtual_lab_has_learning_and_faq_schema(self):
        response = self.client.get("/guides/chemical-reaction-virtual-lab/")
        html = response.content.decode()
        schemas = [
            json.loads(match)
            for match in re.findall(
                r'<script type="application/ld\+json">(.*?)</script>',
                html,
                re.DOTALL,
            )
        ]
        page_graph = next(schema["@graph"] for schema in schemas if "@graph" in schema)
        schema_types = {item["@type"] for item in page_graph}

        self.assertEqual(schema_types, {"LearningResource", "FAQPage"})
        faq_schema = next(item for item in page_graph if item["@type"] == "FAQPage")
        self.assertEqual(len(faq_schema["mainEntity"]), 4)

    def test_guide_library_links_to_chemical_reaction_virtual_lab(self):
        response = self.client.get("/guides/")

        self.assertContains(
            response,
            'href="/guides/chemical-reaction-virtual-lab/"',
        )

    def test_homepage_description_states_audience_action_and_boundary(self):
        response = self.client.get("/")

        self.assertContains(
            response,
            (
                '<meta name="description" content="Explore predicted reactions '
                "in a virtual lab built for chemistry students. OmniLab is "
                "educational and doesn't replace physical lab procedures.\">"
            ),
            html=True,
        )

    def test_homepage_exposes_google_site_verification(self):
        response = self.client.get("/")

        self.assertContains(
            response,
            (
                '<meta name="google-site-verification" '
                'content="pTc0pLcOShqcQfWfDLPq04vaqqyFLVJ22Xq-rKsvH6A" />'
            ),
            html=True,
        )

    def test_all_sitemap_routes_have_distinct_concise_search_metadata(self):
        sitemap = self.client.get("/sitemap.xml").content.decode()
        paths = re.findall(
            r"<loc>https?://[^/]+([^<]*)</loc>",
            sitemap,
        )
        metadata = []

        self.assertEqual(len(paths), 35)
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                html = response.content.decode()
                title_matches = re.findall(
                    r"<title>(.*?)</title>",
                    html,
                    re.DOTALL,
                )
                description_matches = re.findall(
                    r'<meta name="description" content="([^"]*)">',
                    html,
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(title_matches), 1)
                self.assertEqual(len(description_matches), 1)

                title = title_matches[0].strip()
                description = description_matches[0]
                self.assertGreaterEqual(len(title), 30)
                self.assertLessEqual(len(title), 65)
                self.assertGreaterEqual(len(description), 110)
                self.assertLessEqual(len(description), 160)
                metadata.append((title, description))

        titles = [title for title, _description in metadata]
        descriptions = [description for _title, description in metadata]
        self.assertEqual(len(set(titles)), 35)
        self.assertEqual(len(set(descriptions)), 35)
        self.assertNotIn("12 guides", " ".join(descriptions))

    def test_public_pages_use_production_canonical_urls(self):
        routes = {
            "/": "index",
            "/pricing/": "pricing",
            "/contact/": "contact",
            "/faq/": "faq",
            "/guides/": "guides",
            "/privacy/": "privacy",
            "/terms/": "terms",
        }

        for path, page_name in routes.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    f'<link rel="canonical" href="{PUBLIC_CANONICAL_URLS[page_name]}">',
                    html=True,
                )

    def test_robots_txt_points_crawlers_to_sitemap(self):
        response = self.client.get("/robots.txt")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        self.assertContains(response, "User-agent: *")
        self.assertContains(response, "Allow: /")
        self.assertContains(response, "Disallow: /admin/")
        self.assertContains(response, "Disallow: /ai_insights/")
        self.assertContains(
            response,
            f"Sitemap: {PRODUCTION_BASE_URL}/sitemap.xml",
        )

    def test_sitemap_contains_each_public_canonical_once(self):
        response = self.client.get("/sitemap.xml")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/xml"))
        root = ET.fromstring(response.content)
        namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = [
            node.text for node in root.findall("sitemap:url/sitemap:loc", namespace)
        ]
        self.assertEqual(locations, list(PUBLIC_CANONICAL_URLS.values()))

    def test_homepage_has_factual_software_application_schema(self):
        response = self.client.get("/")
        html = response.content.decode()
        schemas = [
            json.loads(match)
            for match in re.findall(
                r'<script type="application/ld\+json">(.*?)</script>',
                html,
                re.DOTALL,
            )
        ]
        software_schema = next(
            schema
            for schema in schemas
            if schema.get("@type") == "SoftwareApplication"
        )

        self.assertEqual(software_schema["name"], "OmniLab")
        self.assertEqual(software_schema["url"], PUBLIC_CANONICAL_URLS["index"])
        self.assertEqual(
            software_schema["applicationCategory"],
            "EducationalApplication",
        )
        self.assertEqual(software_schema["operatingSystem"], "Any")
        self.assertEqual(len(software_schema["featureList"]), 3)
        self.assertNotIn("offers", software_schema)
        self.assertNotIn("aggregateRating", software_schema)
        self.assertNotIn("publisher", software_schema)
        self.assertNotIn("author", software_schema)


class GuidedExperimentPageTests(TestCase):
    routes = {
        "/guides/sodium-and-chlorine-reaction/": "reaction",
        "/guides/sodium-and-chlorine-formula/": "formula",
        "/guides/sodium-and-chlorine-ionic-bond/": "ionic-bond",
    }

    def test_exactly_three_guides_answer_distinct_student_questions(self):
        self.assertEqual(len(GUIDED_EXPERIMENT_PAGES), 3)

        titles = set()
        for path, guide_key in self.routes.items():
            with self.subTest(path=path):
                guide = GUIDED_EXPERIMENT_PAGES[guide_key]
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f"<h1 id=\"guide-heading\">{guide['title']}</h1>", html=True)
                self.assertContains(response, guide["direct_answer"])
                titles.add(guide["title"])

        self.assertEqual(len(titles), 3)

    def test_each_guide_has_one_primary_path_to_the_prepared_lab(self):
        for path, guide_key in self.routes.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                html = response.content.decode()
                visit_source = GUIDED_EXPERIMENT_PAGES[guide_key]["visit_source"]

                self.assertEqual(html.count('class="guide-primary"'), 1)
                self.assertContains(response, "Try Sodium + Chlorine")
                self.assertNotContains(response, "Open the prepared lab")
                self.assertEqual(
                    html.count(
                        'href="/demo/sodium-chlorine/'
                        f'?source={visit_source}"'
                    ),
                    1,
                )

    def test_each_guide_links_to_three_related_chemistry_questions(self):
        for path, guide_key in self.routes.items():
            with self.subTest(path=path):
                guide = GUIDED_EXPERIMENT_PAGES[guide_key]
                html = self.client.get(path).content.decode()
                related_block = html.split(
                    'class="guide-related"', 1
                )[1].split("</nav>", 1)[0]
                relationships = GUIDE_RELATIONSHIPS[
                    guide["canonical_key"]
                ]

                self.assertEqual(related_block.count("<a href="), 3)
                self.assertNotIn(
                    guide["title"],
                    related_block,
                )
                for related_key, reason in relationships:
                    related_guide = GUIDE_PAGE_REFERENCES[related_key]
                    self.assertIn(
                        f'href="{reverse(related_guide["route_name"])}"',
                        related_block,
                    )
                    self.assertIn(related_guide["title"], related_block)
                    self.assertIn(reason, related_block)

    def test_related_questions_stay_secondary_to_the_lab_action(self):
        for path in self.routes:
            with self.subTest(path=path):
                html = self.client.get(path).content.decode()
                related_block = html.split(
                    'class="guide-related"', 1
                )[1].split("</nav>", 1)[0]

                self.assertEqual(html.count('class="guide-primary"'), 1)
                self.assertNotIn('class="guide-primary"', related_block)
                self.assertNotIn('class="btn', related_block)

    def test_each_guide_uses_one_fixed_privacy_safe_analytics_source(self):
        expected_sources = {
            "reaction": "guide_reaction",
            "formula": "guide_formula",
            "ionic-bond": "guide_ionic_bond",
        }

        self.assertEqual(
            {
                key: guide["visit_source"]
                for key, guide in GUIDED_EXPERIMENT_PAGES.items()
            },
            expected_sources,
        )
        for path, guide_key in self.routes.items():
            with self.subTest(path=path):
                visit_source = expected_sources[guide_key]
                response = self.client.get(f"{path}?source=arbitrary-private-value")
                html = response.content.decode()

                self.assertContains(
                    response,
                    f'window.guideVisitSource = "{visit_source}";',
                )
                self.assertContains(
                    response,
                    '<script type="module" src="/static/js/root/guide.js"></script>',
                    html=True,
                )
                self.assertNotContains(response, "arbitrary-private-value")

    def test_guides_use_privacy_limited_product_analytics(self):
        for path in self.routes:
            with self.subTest(path=path):
                response = self.client.get(
                    path,
                    HTTP_HOST="omnilab-bk8q.onrender.com",
                )

                for setting in (
                    "autocapture: false",
                    "capture_pageview: false",
                    "capture_pageleave: false",
                    "capture_performance: false",
                    "disable_session_recording: true",
                ):
                    self.assertContains(response, setting)

    def test_guides_keep_the_educational_and_safety_boundaries_visible(self):
        for path in self.routes:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertContains(
                    response,
                    "It can be incomplete or wrong and does not replace "
                    "instructor supervision, trusted references, or "
                    "physical-lab safety procedures.",
                )
                self.assertContains(
                    response,
                    "Do not attempt the sodium and chlorine reaction outside "
                    "a properly equipped, supervised laboratory.",
                )

    def test_guides_have_unique_canonicals_metadata_and_learning_schema(self):
        canonical_urls = set()
        for path, guide_key in self.routes.items():
            with self.subTest(path=path):
                guide = GUIDED_EXPERIMENT_PAGES[guide_key]
                response = self.client.get(path)
                html = response.content.decode()
                canonical = PUBLIC_CANONICAL_URLS[guide["canonical_key"]]

                self.assertContains(
                    response,
                    f'<link rel="canonical" href="{canonical}">',
                    html=True,
                )
                self.assertContains(
                    response,
                    f'<meta name="description" content="{guide["description"]}">',
                    html=True,
                )
                schema_match = re.search(
                    r'<script type="application/ld\+json">(.*?)</script>',
                    html,
                    re.DOTALL,
                )
                self.assertIsNotNone(schema_match)
                schema = json.loads(schema_match.group(1))
                self.assertEqual(schema["@type"], "LearningResource")
                self.assertEqual(schema["url"], canonical)
                canonical_urls.add(canonical)

        self.assertEqual(len(canonical_urls), 3)

    def test_sitemap_includes_all_three_guides(self):
        sitemap = self.client.get("/sitemap.xml").content.decode()

        for guide in GUIDED_EXPERIMENT_PAGES.values():
            canonical = PUBLIC_CANONICAL_URLS[guide["canonical_key"]]
            with self.subTest(canonical=canonical):
                self.assertEqual(sitemap.count(canonical), 1)


class ObservationGuidePageTests(TestCase):
    routes = {
        "/guides/sulfuric-acid-and-potassium-hydroxide-reaction/": ("sulfuric-acid-potassium-hydroxide", "/demo/sulfuric-acid-potassium-hydroxide/"),
        "/guides/aluminium-chloride-and-sodium-hydroxide-reaction/": ("aluminium-chloride-sodium-hydroxide", "/demo/aluminium-chloride-sodium-hydroxide/"),
        "/guides/magnesium-sulfate-and-sodium-hydroxide-reaction/": ("magnesium-sulfate-sodium-hydroxide", "/demo/magnesium-sulfate-sodium-hydroxide/"),
        "/guides/why-limewater-turns-cloudy-with-carbon-dioxide/": (
            "limewater-carbon-dioxide",
            "/demo/carbon-dioxide-calcium-hydroxide/",
        ),
        "/guides/why-sodium-carbonate-fizzes-with-hydrochloric-acid/": (
            "sodium-carbonate-hydrochloric-acid",
            "/demo/sodium-carbonate-hydrochloric-acid/",
        ),
        "/guides/silver-nitrate-potassium-iodide-precipitate/": (
            "silver-nitrate-potassium-iodide",
            "/demo/silver-nitrate-potassium-iodide/",
        ),
        "/guides/copper-ii-sulfate-potassium-hydroxide-precipitate/": (
            "copper-sulfate-potassium-hydroxide",
            "/demo/copper-sulfate-potassium-hydroxide/",
        ),
        "/guides/reaction-of-sodium-in-water/": (
            "sodium-water",
            "/demo/sodium-water/",
        ),
        "/guides/zinc-and-hydrochloric-acid-reaction/": (
            "zinc-hydrochloric-acid",
            "/demo/zinc-hydrochloric-acid/",
        ),
        "/guides/acetic-acid-and-sodium-bicarbonate-reaction/": (
            "acetic-acid-sodium-bicarbonate",
            "/demo/acetic-acid-sodium-bicarbonate/",
        ),
        "/guides/hydrogen-and-oxygen-reaction/": (
            "hydrogen-oxygen",
            "/demo/hydrogen-oxygen/",
        ),
        "/guides/reaction-of-iron-with-oxygen/": (
            "iron-oxygen",
            "/demo/iron-oxygen/",
        ),
        "/guides/reaction-of-copper-with-oxygen/": (
            "copper-oxygen",
            "/demo/copper-oxygen/",
        ),
        "/guides/hydrochloric-acid-and-sodium-hydroxide-reaction/": (
            "hydrochloric-acid-sodium-hydroxide",
            "/demo/hydrochloric-acid-sodium-hydroxide/",
        ),
        "/guides/silver-nitrate-and-sodium-chloride-reaction/": (
            "silver-nitrate-sodium-chloride",
            "/demo/silver-nitrate-sodium-chloride/",
        ),
        "/guides/carbon-monoxide-and-oxygen-reaction/": (
            "carbon-monoxide-oxygen",
            "/demo/carbon-monoxide-oxygen/",
        ),
        "/guides/carbon-dioxide-and-water-reaction/": (
            "carbon-dioxide-water",
            "/demo/carbon-dioxide-water/",
        ),
        "/guides/nitrogen-dioxide-and-water-reaction/": (
            "nitrogen-dioxide-water",
            "/demo/nitrogen-dioxide-water/",
        ),
        "/guides/hydrogen-and-chlorine-reaction/": (
            "hydrogen-chlorine",
            "/demo/hydrogen-chlorine/",
        ),
        "/guides/carbon-and-oxygen-reaction/": (
            "carbon-oxygen",
            "/demo/carbon-oxygen/",
        ),
        "/guides/iron-and-hydrochloric-acid-reaction/": (
            "iron-hydrochloric-acid",
            "/demo/iron-hydrochloric-acid/",
        ),
        "/guides/potassium-permanganate-and-hydrogen-peroxide-reaction/": (
            "potassium-permanganate-hydrogen-peroxide",
            "/demo/potassium-permanganate-hydrogen-peroxide/",
        ),
        "/guides/sodium-chloride-and-water-reaction/": (
            "sodium-chloride-water",
            "/demo/sodium-chloride-water/",
        ),
        "/guides/carbon-dioxide-and-sodium-hydroxide-reaction/": (
            "carbon-dioxide-sodium-hydroxide",
            "/demo/carbon-dioxide-sodium-hydroxide/",
        ),
    }

    def test_twenty_four_guides_match_the_confirmed_reaction_matrix(self):
        self.assertEqual(len(OBSERVATION_GUIDE_PAGES), 24)

        for path, (guide_key, _demo_path) in self.routes.items():
            with self.subTest(path=path):
                guide = OBSERVATION_GUIDE_PAGES[guide_key]
                selected_chemicals = [
                    reactant["formula"] for reactant in guide["reactants"]
                ]
                reaction = get_reaction(selected_chemicals)
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(guide["equation"], reaction["equation"])
                self.assertEqual(guide["explanation"], reaction["explanation"])
                self.assertEqual(guide["safety"], reaction["safety"].split(" | "))
                self.assertEqual(len(guide["safety"]), 3)
                self.assertContains(response, guide["title"])
                self.assertContains(response, guide["direct_answer"])
                self.assertIn(
                    guide["equation"].replace(">", "&gt;"),
                    response.content.decode(),
                )
                self.assertContains(response, guide["explanation"])
                for safety_note in guide["safety"]:
                    self.assertContains(response, safety_note)

    def test_carbon_dioxide_sodium_hydroxide_guide_answers_query_completely(self):
        response = self.client.get(
            "/guides/carbon-dioxide-and-sodium-hydroxide-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            (
                "<title>Carbon dioxide and sodium hydroxide reaction | "
                "OmniLab</title>"
            ),
            html=True,
        )
        self.assertContains(
            response,
            "Carbon dioxide reacts with excess sodium hydroxide to form sodium carbonate and water.",
        )
        self.assertIn(
            "CO2(g) + 2NaOH(aq) -&gt; Na2CO3(aq) + H2O(l)",
            html,
        )
        self.assertContains(response, "A 1:1 ratio can instead favor sodium bicarbonate.")
        self.assertContains(response, "No dramatic visible change")
        self.assertContains(
            response,
            (
                'href="/demo/carbon-dioxide-sodium-hydroxide/'
                '?source=guide_virtual_lab"'
            ),
            html=False,
        )
        self.assertEqual(
            html.count('class="guide-related-link-copy"'),
            3,
        )
        self.assertContains(response, "What forms when CO2 reacts with NaOH?")

    def test_carbon_dioxide_sodium_hydroxide_has_three_reciprocal_neighbors(self):
        guide_key = "carbon_dioxide_sodium_hydroxide"
        neighbors = {
            "carbon_dioxide_water",
            "limewater_carbon_dioxide",
            "hydrochloric_acid_sodium_hydroxide",
        }

        self.assertEqual(
            {key for key, _reason in GUIDE_RELATIONSHIPS[guide_key]},
            neighbors,
        )
        for neighbor in neighbors:
            with self.subTest(neighbor=neighbor):
                self.assertIn(
                    guide_key,
                    {
                        key
                        for key, _reason in GUIDE_RELATIONSHIPS[neighbor]
                    },
                )

    def test_sodium_water_guide_answers_the_target_query_completely(self):
        response = self.client.get("/guides/reaction-of-sodium-in-water/")
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<title>Sodium reacts with water: equation and result | OmniLab</title>",
            html=True,
        )
        self.assertContains(
            response,
            "Sodium reacts with water to form sodium hydroxide and hydrogen gas.",
        )
        self.assertIn(
            "2Na(s) + 2H2O(l) -&gt; 2NaOH(aq) + H2(g)",
            html,
        )
        self.assertContains(response, "Three details that explain the result")
        self.assertContains(response, "From floating metal to an alkaline solution")
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )
        for item in OBSERVATION_GUIDE_PAGES["sodium-water"][
            "common_questions"
        ]:
            self.assertContains(response, item["question"])
            self.assertContains(response, item["answer"])

    def test_zinc_hydrochloric_acid_guide_answers_the_target_query_completely(self):
        response = self.client.get(
            "/guides/zinc-and-hydrochloric-acid-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<title>Zinc and hydrochloric acid reaction | OmniLab</title>",
            html=True,
        )
        self.assertContains(
            response,
            "Zinc reacts with hydrochloric acid to form zinc chloride and hydrogen gas.",
        )
        self.assertIn(
            "Zn(s) + 2HCl(aq) -&gt; ZnCl2(aq) + H2(g)",
            html,
        )
        self.assertContains(response, "Your study goal:")
        self.assertContains(response, "Three details that explain the result")
        self.assertContains(response, "Hydrogen bubbles as zinc is consumed")
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_acetic_acid_sodium_bicarbonate_guide_answers_query_completely(self):
        response = self.client.get(
            "/guides/acetic-acid-and-sodium-bicarbonate-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            (
                "<title>Acetic acid and sodium bicarbonate reaction | "
                "OmniLab</title>"
            ),
            html=True,
        )
        self.assertContains(
            response,
            "Acetic acid reacts with sodium bicarbonate to form sodium acetate",
        )
        self.assertIn(
            "CH3COOH(aq) + NaHCO3(s) -&gt; "
            "CH3COONa(aq) + CO2(g) + H2O(l)",
            html,
        )
        self.assertContains(response, "Your study goal:")
        self.assertContains(response, "Three details that explain the result")
        self.assertContains(response, "Carbon dioxide bubbles and visible fizzing")
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_hydrogen_oxygen_guide_answers_the_target_query_completely(self):
        response = self.client.get(
            "/guides/hydrogen-and-oxygen-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            (
                "<title>Hydrogen and oxygen reaction: equation and result | "
                "OmniLab</title>"
            ),
            html=True,
        )
        self.assertContains(
            response,
            "Hydrogen reacts with oxygen to form water when the mixture is initiated.",
        )
        self.assertIn(
            "2H2(g) + O2(g) -&gt; 2H2O(l)",
            html,
        )
        self.assertContains(response, "Your study goal:")
        self.assertContains(response, "Three details that explain the result")
        self.assertContains(
            response,
            "Water forms in a strongly exothermic reaction",
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_three_priority_guides_open_with_answer_equation_and_boundary(self):
        priority_routes = {
            "/guides/zinc-and-hydrochloric-acid-reaction/": (
                "zinc-hydrochloric-acid",
                "/demo/zinc-hydrochloric-acid/?source=guide_virtual_lab",
            ),
            "/guides/acetic-acid-and-sodium-bicarbonate-reaction/": (
                "acetic-acid-sodium-bicarbonate",
                "/demo/acetic-acid-sodium-bicarbonate/?source=guide_virtual_lab",
            ),
            "/guides/hydrogen-and-oxygen-reaction/": (
                "hydrogen-oxygen",
                "/demo/hydrogen-oxygen/?source=guide_virtual_lab",
            ),
        }

        for path, (guide_key, demo_path) in priority_routes.items():
            with self.subTest(path=path):
                guide = OBSERVATION_GUIDE_PAGES[guide_key]
                response = self.client.get(path)
                html = response.content.decode()

                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    f'<meta name="description" content="{guide["description"]}">',
                    html=True,
                )
                self.assertContains(response, 'aria-label="Answer at a glance"')
                self.assertContains(response, guide["opening_boundary"])
                self.assertContains(
                    response,
                    f'href="{demo_path}"',
                )

                heading_index = html.index(guide["title"])
                answer_index = html.index(guide["direct_answer"])
                equation_index = html.index(
                    guide["equation"].replace(">", "&gt;")
                )
                boundary_index = html.index(guide["opening_boundary"])
                action_index = html.index(f'href="{demo_path}"')
                self.assertLess(heading_index, answer_index)
                self.assertLess(answer_index, equation_index)
                self.assertLess(equation_index, boundary_index)
                self.assertLess(boundary_index, action_index)

    def test_iron_oxygen_guide_answers_the_target_query_completely(self):
        response = self.client.get(
            "/guides/reaction-of-iron-with-oxygen/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            (
                "<title>Reaction of iron with oxygen: equation and result | "
                "OmniLab</title>"
            ),
            html=True,
        )
        self.assertContains(
            response,
            "Iron reacts with oxygen to form iron oxide.",
        )
        self.assertIn(
            "4Fe(s) + 3O2(g) -&gt; 2Fe2O3(s)",
            html,
        )
        self.assertContains(response, "Your study goal:")
        self.assertContains(response, "Three details that explain the result")
        self.assertContains(
            response,
            (
                "Connect the coefficients and formulas to the products, "
                "electron transfer, and expected observation."
            ),
        )
        self.assertContains(response, "A solid iron oxide product")
        self.assertContains(response, "Why do some equations show Fe3O4 instead?")
        self.assertContains(response, "observation-oxide")
        self.assertEqual(
            html.count('href="/guides/chemical-reaction-virtual-lab/"'),
            1,
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_copper_oxygen_guide_answers_the_target_query_completely(self):
        response = self.client.get(
            "/guides/reaction-of-copper-with-oxygen/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            (
                "<title>Reaction of copper with oxygen: equation and result "
                "| OmniLab</title>"
            ),
            html=True,
        )
        self.assertContains(
            response,
            "When copper is heated in oxygen, it forms black copper(II) oxide.",
        )
        self.assertIn("2Cu(s) + O2(g) -&gt; 2CuO(s)", html)
        self.assertContains(response, "A black copper(II) oxide coating")
        self.assertContains(response, "Can copper form a different oxide?")
        self.assertContains(response, "Why can the copper sample gain mass?")
        self.assertContains(
            response,
            (
                'href="/demo/copper-oxygen/'
                '?source=guide_virtual_lab"'
            ),
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_potassium_permanganate_hydrogen_peroxide_guide_answers_query(self):
        response = self.client.get(
            "/guides/potassium-permanganate-and-hydrogen-peroxide-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            (
                "<title>Potassium permanganate and hydrogen peroxide reaction "
                "| OmniLab</title>"
            ),
            html=True,
        )
        self.assertContains(
            response,
            "In neutral or alkaline conditions, potassium permanganate",
        )
        self.assertIn(
            (
                "2KMnO4(aq) + 3H2O2(aq) -&gt; 2MnO2(s) + 3O2(g) + "
                "2KOH(aq) + 2H2O(l)"
            ),
            html,
        )
        self.assertContains(
            response,
            "Oxygen bubbles and brown manganese dioxide",
        )
        self.assertContains(
            response,
            "Why do acidic conditions give a different equation?",
        )
        self.assertContains(response, "does not render the brown solid")
        self.assertContains(
            response,
            (
                'href="/demo/potassium-permanganate-hydrogen-peroxide/'
                '?source=guide_virtual_lab"'
            ),
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_hydrochloric_acid_sodium_hydroxide_guide_answers_query_completely(
        self,
    ):
        response = self.client.get(
            "/guides/hydrochloric-acid-and-sodium-hydroxide-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            (
                "<title>Hydrochloric acid and sodium hydroxide reaction | "
                "OmniLab</title>"
            ),
            html=True,
        )
        self.assertContains(
            response,
            (
                "Hydrochloric acid and sodium hydroxide neutralize to form "
                "sodium chloride and water."
            ),
        )
        self.assertIn(
            "HCl(aq) + NaOH(aq) -&gt; NaCl(aq) + H2O(l)",
            html,
        )
        self.assertContains(response, "Your study goal:")
        self.assertContains(response, "Three details that explain the result")
        self.assertContains(response, "A clear solution that can warm")
        self.assertContains(response, "What is the net ionic equation?")
        self.assertContains(
            response,
            "The model leaves out concentration, volume, temperature, pH",
        )
        self.assertContains(
            response,
            (
                'href="/demo/hydrochloric-acid-sodium-hydroxide/'
                '?source=guide_virtual_lab"'
            ),
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_silver_nitrate_sodium_chloride_guide_answers_query_completely(self):
        response = self.client.get(
            "/guides/silver-nitrate-and-sodium-chloride-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            (
                "<title>Silver nitrate and sodium chloride reaction | "
                "OmniLab</title>"
            ),
            html=True,
        )
        self.assertContains(
            response,
            (
                "Silver nitrate and sodium chloride form silver chloride, an "
                "insoluble white precipitate."
            ),
        )
        self.assertIn(
            "AgNO3(aq) + NaCl(aq) -&gt; AgCl(s) + NaNO3(aq)",
            html,
        )
        self.assertIn(
            "Ag+(aq) + Cl-(aq) -&gt; AgCl(s)",
            html,
        )
        self.assertContains(response, "A white silver chloride precipitate")
        self.assertContains(response, "What type of reaction is AgNO3 with NaCl?")
        self.assertContains(
            response,
            (
                'href="/demo/silver-nitrate-sodium-chloride/'
                '?source=guide_virtual_lab"'
            ),
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_carbon_monoxide_oxygen_guide_keeps_activation_with_the_answer(self):
        response = self.client.get(
            "/guides/carbon-monoxide-and-oxygen-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<title>Carbon monoxide and oxygen reaction | OmniLab</title>",
            html=True,
        )
        self.assertContains(
            response,
            "after ignition or catalytic activation",
        )
        self.assertIn("2CO(g) + O2(g) -&gt; 2CO2(g)", html)
        self.assertContains(response, "No simulated flame or ignition cue")
        self.assertContains(
            response,
            "Treat carbon monoxide and oxygen as a flammable, potentially explosive mixture.",
        )
        self.assertContains(
            response,
            (
                'href="/demo/carbon-monoxide-oxygen/'
                '?source=guide_virtual_lab"'
            ),
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_carbon_dioxide_water_guide_keeps_equilibrium_with_the_answer(self):
        response = self.client.get(
            "/guides/carbon-dioxide-and-water-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<title>Carbon dioxide and water reaction | OmniLab</title>",
            html=True,
        )
        self.assertContains(
            response,
            "a small fraction reacts reversibly to form carbonic acid",
        )
        self.assertIn("CO2(g) + H2O(l) -&gt; H2CO3(aq)", html)
        self.assertContains(
            response,
            "A clear solution with no dramatic color change",
        )
        self.assertContains(
            response,
            "The equation is a simplified model of an equilibrium",
        )
        self.assertContains(
            response,
            (
                'href="/demo/carbon-dioxide-water/'
                '?source=guide_virtual_lab"'
            ),
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_nitrogen_dioxide_water_guide_keeps_caveats_with_the_answer(self):
        response = self.client.get(
            "/guides/nitrogen-dioxide-and-water-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<title>Nitrogen dioxide and water reaction | OmniLab</title>",
            html=True,
        )
        self.assertContains(
            response,
            "The products are nitrous acid and nitric acid.",
        )
        self.assertIn(
            "2NO2(g) + H2O(l) -&gt; HNO2(aq) + HNO3(aq)",
            html,
        )
        self.assertContains(
            response,
            "Real absorption involves equilibria and further chemistry.",
        )
        self.assertContains(
            response,
            "Why do some equations show nitric oxide?",
        )
        self.assertContains(
            response,
            "Less brown gas above a clear acidic solution",
        )
        self.assertContains(
            response,
            (
                'href="/demo/nitrogen-dioxide-water/'
                '?source=guide_virtual_lab"'
            ),
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_nitrogen_dioxide_water_has_two_reciprocal_neighbors(self):
        guide_key = "nitrogen_dioxide_water"
        neighbors = {
            "carbon_dioxide_water",
            "potassium_permanganate_hydrogen_peroxide",
        }

        self.assertEqual(
            {key for key, _reason in GUIDE_RELATIONSHIPS[guide_key]},
            neighbors,
        )
        for neighbor in neighbors:
            with self.subTest(neighbor=neighbor):
                self.assertIn(
                    guide_key,
                    {
                        key
                        for key, _reason in GUIDE_RELATIONSHIPS[neighbor]
                    },
                )

    def test_hydrogen_chlorine_guide_keeps_initiation_with_the_answer(self):
        response = self.client.get(
            "/guides/hydrogen-and-chlorine-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<title>Hydrogen and chlorine reaction | OmniLab</title>",
            html=True,
        )
        self.assertContains(
            response,
            "Hydrogen reacts with chlorine after initiation",
        )
        self.assertIn("H2(g) + Cl2(g) -&gt; 2HCl(g)", html)
        self.assertContains(
            response,
            "Light or heat can initiate a rapid chain reaction.",
        )
        self.assertContains(
            response,
            "Is hydrogen chloride the same as hydrochloric acid?",
        )
        self.assertContains(
            response,
            "No simulated flash, flame, or pressure change",
        )
        self.assertContains(
            response,
            (
                'href="/demo/hydrogen-chlorine/'
                '?source=guide_virtual_lab"'
            ),
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_hydrogen_chlorine_has_two_reciprocal_neighbors(self):
        guide_key = "hydrogen_chlorine"
        neighbors = {"hydrogen_oxygen", "sodium_chlorine_reaction"}

        self.assertEqual(
            {key for key, _reason in GUIDE_RELATIONSHIPS[guide_key]},
            neighbors,
        )
        for neighbor in neighbors:
            with self.subTest(neighbor=neighbor):
                self.assertIn(
                    guide_key,
                    {
                        key
                        for key, _reason in GUIDE_RELATIONSHIPS[neighbor]
                    },
                )

    def test_carbon_oxygen_guide_keeps_oxygen_supply_with_the_answer(self):
        response = self.client.get(
            "/guides/carbon-and-oxygen-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<title>Carbon and oxygen reaction | OmniLab</title>",
            html=True,
        )
        self.assertContains(
            response,
            "In sufficient oxygen, carbon burns to form carbon dioxide.",
        )
        self.assertIn("C(s) + O2(g) -&gt; CO2(g)", html)
        self.assertContains(
            response,
            "Carbon needs ignition or strong heating before it burns.",
        )
        self.assertContains(
            response,
            "What happens when oxygen is limited?",
        )
        self.assertContains(
            response,
            "No simulated glow, flame, or gas buildup",
        )
        self.assertContains(
            response,
            'href="/demo/carbon-oxygen/?source=guide_virtual_lab"',
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_carbon_oxygen_has_two_reciprocal_neighbors(self):
        guide_key = "carbon_oxygen"
        neighbors = {"carbon_monoxide_oxygen", "iron_oxygen"}

        self.assertEqual(
            {key for key, _reason in GUIDE_RELATIONSHIPS[guide_key]},
            neighbors,
        )
        for neighbor in neighbors:
            with self.subTest(neighbor=neighbor):
                self.assertIn(
                    guide_key,
                    {
                        key
                        for key, _reason in GUIDE_RELATIONSHIPS[neighbor]
                    },
                )

    def test_iron_hydrochloric_acid_guide_answers_the_target_query(self):
        response = self.client.get(
            "/guides/iron-and-hydrochloric-acid-reaction/"
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<title>Iron and hydrochloric acid reaction | OmniLab</title>",
            html=True,
        )
        self.assertContains(
            response,
            "Iron reacts with hydrochloric acid to form iron(II) chloride",
        )
        self.assertIn("Fe(s) + 2HCl(aq) -&gt; FeCl2(aq) + H2(g)", html)
        self.assertContains(response, "Hydrogen bubbles at the iron surface")
        self.assertContains(
            response,
            "It does not model acid concentration",
        )
        self.assertContains(
            response,
            (
                'href="/demo/iron-hydrochloric-acid/'
                '?source=guide_virtual_lab"'
            ),
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_sodium_chloride_water_guide_answers_the_target_query(self):
        path = "/guides/sodium-chloride-and-water-reaction/"
        response = self.client.get(path)
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<title>Sodium chloride and water reaction | OmniLab</title>",
            html=True,
        )
        self.assertContains(
            response,
            "Sodium chloride does not form a new compound when it mixes with water.",
        )
        self.assertIn(
            "NaCl(s) + H2O(l) -&gt; Na+(aq) + Cl-(aq) + H2O(l)",
            html,
        )
        self.assertContains(response, "A clear solution with dissolved ions")
        self.assertContains(
            response,
            "This is dissolution and ionic dissociation",
        )
        self.assertContains(
            response,
            (
                'href="/demo/sodium-chloride-water/'
                '?source=guide_virtual_lab"'
            ),
        )
        self.assertEqual(
            html.count('class="observation-guide-question-list"'),
            1,
        )

    def test_sodium_chloride_water_has_three_reciprocal_neighbors(self):
        guide_key = "sodium_chloride_water"
        neighbors = {
            "sodium_chlorine_formula",
            "hydrochloric_acid_sodium_hydroxide",
            "silver_nitrate_sodium_chloride",
        }

        self.assertEqual(
            {key for key, _reason in GUIDE_RELATIONSHIPS[guide_key]},
            neighbors,
        )
        for neighbor in neighbors:
            with self.subTest(neighbor=neighbor):
                self.assertIn(
                    guide_key,
                    {
                        key
                        for key, _reason in GUIDE_RELATIONSHIPS[neighbor]
                    },
                )

    def test_each_guide_has_one_exact_prepared_lab_action(self):
        for path, (guide_key, demo_path) in self.routes.items():
            with self.subTest(path=path):
                guide = OBSERVATION_GUIDE_PAGES[guide_key]
                html = self.client.get(path).content.decode()

                self.assertEqual(html.count('class="guide-primary"'), 1)
                self.assertEqual(
                    html.count(
                        f'href="{demo_path}?source={guide["visit_source"]}"'
                    ),
                    1,
                )
                self.assertIn(
                    "Nothing runs until you select Analyze.",
                    html,
                )

    def test_prepared_demos_select_the_exact_pair_without_auto_analysis(self):
        for _path, (guide_key, demo_path) in self.routes.items():
            with self.subTest(demo_path=demo_path):
                guide = OBSERVATION_GUIDE_PAGES[guide_key]
                demo_key = demo_path.removeprefix("/demo/").removesuffix("/")
                demo = REACTION_DEMOS[demo_key]
                response = self.client.get(
                    f"{demo_path}?source={guide['visit_source']}"
                )
                html = response.content.decode()
                selected_chemicals = [
                    reactant["formula"] for reactant in guide["reactants"]
                ]

                self.assertEqual(response.status_code, 200)
                self.assertEqual(demo["selectedChemicals"], selected_chemicals)
                self.assertContains(
                    response,
                    f"window.reactionDemo = {json.dumps(demo)};",
                )
                self.assertNotIn("fireAIAnalysis()", html)
                self.assertContains(response, "Analyze Chemical Reaction")

    def test_guides_use_fixed_sources_and_ignore_query_values(self):
        expected_sources = {
            "sulfuric-acid-potassium-hydroxide": "guide_virtual_lab",
            "aluminium-chloride-sodium-hydroxide": "guide_virtual_lab",
            "magnesium-sulfate-sodium-hydroxide": "guide_virtual_lab",
            "limewater-carbon-dioxide": "guide_observation_a",
            "sodium-carbonate-hydrochloric-acid": "guide_observation_b",
            "silver-nitrate-potassium-iodide": "guide_observation_c",
            "copper-sulfate-potassium-hydroxide": "guide_observation_d",
            "sodium-water": "guide_observation_e",
            "zinc-hydrochloric-acid": "guide_virtual_lab",
            "acetic-acid-sodium-bicarbonate": "guide_virtual_lab",
            "hydrogen-oxygen": "guide_virtual_lab",
            "iron-oxygen": "guide_virtual_lab",
            "copper-oxygen": "guide_virtual_lab",
            "hydrochloric-acid-sodium-hydroxide": "guide_virtual_lab",
            "silver-nitrate-sodium-chloride": "guide_virtual_lab",
            "carbon-monoxide-oxygen": "guide_virtual_lab",
            "carbon-dioxide-water": "guide_virtual_lab",
            "iron-hydrochloric-acid": "guide_virtual_lab",
            "potassium-permanganate-hydrogen-peroxide": "guide_virtual_lab",
            "sodium-chloride-water": "guide_virtual_lab",
            "carbon-dioxide-sodium-hydroxide": "guide_virtual_lab",
            "nitrogen-dioxide-water": "guide_virtual_lab",
            "hydrogen-chlorine": "guide_virtual_lab",
            "carbon-oxygen": "guide_virtual_lab",
        }
        self.assertEqual(
            {
                key: guide["visit_source"]
                for key, guide in OBSERVATION_GUIDE_PAGES.items()
            },
            expected_sources,
        )

        for path, (guide_key, _demo_path) in self.routes.items():
            with self.subTest(path=path):
                response = self.client.get(
                    f"{path}?source=student-email@example.com"
                )
                self.assertContains(
                    response,
                    "window.guideVisitSource = "
                    f'"{expected_sources[guide_key]}";',
                )
                self.assertNotContains(response, "student-email@example.com")

    def test_guides_link_to_two_or_three_relevant_next_questions(self):
        for path, (guide_key, _demo_path) in self.routes.items():
            with self.subTest(path=path):
                guide = OBSERVATION_GUIDE_PAGES[guide_key]
                html = self.client.get(path).content.decode()
                related_block = html.split(
                    'aria-label="Related observation guides"', 1
                )[1].split("</nav>", 1)[0]
                relationships = GUIDE_RELATIONSHIPS[
                    guide["canonical_key"]
                ]

                self.assertIn(len(relationships), (2, 3))
                self.assertEqual(
                    related_block.count("<a href="),
                    len(relationships),
                )
                self.assertNotIn(path, related_block)
                for related_key, reason in relationships:
                    related_guide = GUIDE_PAGE_REFERENCES[related_key]
                    self.assertIn(
                        f'href="{reverse(related_guide["route_name"])}"',
                        related_block,
                    )
                    self.assertIn(related_guide["title"], related_block)
                    self.assertIn(reason, related_block)

    def test_canonicals_schema_and_sitemap_include_each_guide_once(self):
        sitemap = self.client.get("/sitemap.xml").content.decode()
        canonical_urls = set()

        for path, (guide_key, _demo_path) in self.routes.items():
            with self.subTest(path=path):
                guide = OBSERVATION_GUIDE_PAGES[guide_key]
                response = self.client.get(path)
                html = response.content.decode()
                canonical = PUBLIC_CANONICAL_URLS[guide["canonical_key"]]
                schema_match = re.search(
                    r'<script type="application/ld\+json">(.*?)</script>',
                    html,
                    re.DOTALL,
                )

                self.assertContains(
                    response,
                    f'<link rel="canonical" href="{canonical}">',
                    html=True,
                )
                self.assertIsNotNone(schema_match)
                schema = json.loads(schema_match.group(1))
                self.assertEqual(schema["@type"], "LearningResource")
                self.assertEqual(schema["url"], canonical)
                self.assertEqual(sitemap.count(canonical), 1)
                canonical_urls.add(canonical)

        self.assertEqual(len(canonical_urls), 24)

    def test_copper_guide_explains_the_net_ionic_equation(self):
        response = self.client.get(
            "/guides/"
            "copper-ii-sulfate-potassium-hydroxide-precipitate/"
        )

        self.assertContains(response, "Which ions actually form the precipitate?")
        self.assertContains(
            response,
            "Cu2+(aq) + 2OH-(aq) -&gt; Cu(OH)2(s)",
            html=False,
        )
        self.assertContains(response, "K+(aq) and SO4^2-(aq)")
        self.assertContains(response, "Split the soluble reactants into ions")


class GuideStructuredDataContractTests(TestCase):
    @staticmethod
    def _schema(response):
        html = response.content.decode()
        match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if match is None:
            raise AssertionError("Guide page has no JSON-LD block")
        return html, json.loads(match.group(1))

    def _assert_learning_resource(
        self,
        response,
        guide,
        learning_resource,
        canonical,
        equations,
        safety_content,
    ):
        html = response.content.decode()
        expected_name = guide.get("heading", guide["title"])

        self.assertEqual(learning_resource["@type"], "LearningResource")
        self.assertEqual(learning_resource["@id"], f"{canonical}#guide")
        self.assertEqual(learning_resource["url"], canonical)
        self.assertEqual(learning_resource["name"], expected_name)
        self.assertEqual(
            learning_resource["description"],
            guide.get("direct_answer", guide["description"]),
        )
        self.assertIn(expected_name, html)
        self.assertIn(learning_resource["description"], html)

        parts = learning_resource["hasPart"]
        equation_parts = [
            item for item in parts if item["name"] == "Reaction equation"
        ]
        self.assertEqual(
            [item["text"] for item in equation_parts],
            list(equations),
        )
        for equation in equations:
            self.assertIn(equation, html)

        safety_part = next(
            item
            for item in parts
            if item["name"] == "Safety and educational boundary"
        )
        for statement in safety_content:
            self.assertIn(statement, safety_part["text"])
            self.assertIn(statement, html)

    def test_all_twenty_seven_reaction_guides_match_visible_content(self):
        guide_sets = (
            (
                GUIDED_EXPERIMENT_PAGES,
                (
                    GUIDED_EXPERIMENT_BOUNDARY,
                    GUIDED_EXPERIMENT_SAFETY_WARNING,
                ),
            ),
            (OBSERVATION_GUIDE_PAGES, None),
        )

        checked_canonicals = set()
        for guides, shared_safety in guide_sets:
            for guide in guides.values():
                canonical = PUBLIC_CANONICAL_URLS[guide["canonical_key"]]
                path = reverse(guide["route_name"])
                with self.subTest(path=path):
                    response = self.client.get(path)
                    _html, schema = self._schema(response)
                    safety_content = shared_safety or (
                        *guide["safety"],
                        guide["boundary"],
                        OBSERVATION_GUIDE_SAFETY_WARNING,
                    )

                    self._assert_learning_resource(
                        response,
                        guide,
                        schema,
                        canonical,
                        (guide["equation"],),
                        safety_content,
                    )
                    question = schema["mainEntity"]
                    self.assertEqual(question["@type"], "Question")
                    self.assertEqual(question["name"], guide["title"])
                    self.assertEqual(
                        question["acceptedAnswer"],
                        {"@type": "Answer", "text": guide["direct_answer"]},
                    )
                    checked_canonicals.add(canonical)

        self.assertEqual(len(checked_canonicals), 27)

    def test_virtual_lab_guide_schema_matches_examples_faq_and_safety(self):
        guide = CHEMICAL_REACTION_VIRTUAL_LAB_PAGE
        canonical = PUBLIC_CANONICAL_URLS[guide["canonical_key"]]
        response = self.client.get(reverse(guide["route_name"]))
        html, schema = self._schema(response)
        learning_resource = next(
            item
            for item in schema["@graph"]
            if item["@type"] == "LearningResource"
        )
        faq_page = next(
            item
            for item in schema["@graph"]
            if item["@type"] == "FAQPage"
        )
        equations = tuple(
            example["equation"] for example in guide["reaction_examples"]
        )
        safety_content = (
            guide["boundary"],
            guide["safety_boundary"],
            guide["safety_warning"],
        )

        self._assert_learning_resource(
            response,
            guide,
            learning_resource,
            canonical,
            equations,
            safety_content,
        )
        self.assertNotIn("mainEntity", learning_resource)
        self.assertEqual(faq_page["@id"], f"{canonical}#faq")
        for question in faq_page["mainEntity"]:
            self.assertIn(question["name"], html)
            self.assertIn(question["acceptedAnswer"]["text"], html)


class SocialPreviewTests(TestCase):
    def setUp(self):
        self.response = self.client.get("/")

    def test_homepage_exposes_absolute_open_graph_metadata(self):
        tags = (
            '<meta property="og:type" content="website">',
            '<meta property="og:site_name" content="OmniLab">',
            (
                '<meta property="og:title" content="OmniLab - Test chemical '
                'reactions in a virtual lab">'
            ),
            (
                '<meta property="og:description" content="Explore predicted '
                "reactions in a virtual lab built for chemistry students. "
                "OmniLab is educational and doesn't replace physical lab "
                'procedures.">'
            ),
            f'<meta property="og:url" content="{PUBLIC_CANONICAL_URLS["index"]}">',
            f'<meta property="og:image" content="{SOCIAL_PREVIEW_URL}">',
            f'<meta property="og:image:secure_url" content="{SOCIAL_PREVIEW_URL}">',
            '<meta property="og:image:type" content="image/png">',
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
            f'<meta property="og:image:alt" content="{SOCIAL_PREVIEW_ALT}">',
        )

        for tag in tags:
            with self.subTest(tag=tag):
                self.assertContains(self.response, tag, html=True)

        self.assertTrue(SOCIAL_PREVIEW_URL.startswith(f"{PRODUCTION_BASE_URL}/"))

    def test_homepage_exposes_large_twitter_card_metadata(self):
        tags = (
            '<meta name="twitter:card" content="summary_large_image">',
            (
                '<meta name="twitter:title" content="OmniLab - Test chemical '
                'reactions in a virtual lab">'
            ),
            (
                '<meta name="twitter:description" content="Explore predicted '
                "reactions in a virtual lab built for chemistry students. "
                "OmniLab is educational and doesn't replace physical lab "
                'procedures.">'
            ),
            f'<meta name="twitter:image" content="{SOCIAL_PREVIEW_URL}">',
            f'<meta name="twitter:image:alt" content="{SOCIAL_PREVIEW_ALT}">',
        )

        for tag in tags:
            with self.subTest(tag=tag):
                self.assertContains(self.response, tag, html=True)

    def test_social_preview_asset_is_1200_by_630_and_compressed(self):
        asset_path = (
            settings.BASE_DIR / "static/images/omnilab-social-preview.png"
        )
        image_bytes = asset_path.read_bytes()

        self.assertEqual(image_bytes[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", image_bytes[16:24]), (1200, 630))
        self.assertLess(len(image_bytes), 200_000)


class AnalyticsInstrumentationTests(TestCase):
    def test_homepage_uses_privacy_limited_posthog_configuration(self):
        response = self.client.get(
            "/",
            HTTP_HOST="omnilab-bk8q.onrender.com",
        )

        for setting in (
            "autocapture: false",
            "capture_pageview: false",
            "capture_pageleave: false",
            "capture_performance: false",
            "disable_session_recording: true",
        ):
            with self.subTest(setting=setting):
                self.assertContains(response, setting)

        self.assertContains(
            response,
            '<script type="module" src="/static/js/root/main.js"></script>',
            html=True,
        )

    def test_live_posthog_follows_the_default_public_origin_hostname(self):
        analytics_paths = (
            "/",
            "/guides/",
            "/guides/sodium-and-chlorine-reaction/",
            "/guides/chemical-reaction-virtual-lab/",
            "/guides/why-limewater-turns-cloudy-with-carbon-dioxide/",
        )
        live_analytics_markers = (
            "posthog.init(",
            "https://us.i.posthog.com",
            "phc_qHnj5nPFZW9VcTqT82jtjsEHkQk6PTh8g65RrqUBSST7",
        )

        for hostname in ("testserver", "localhost"):
            for path in analytics_paths:
                with self.subTest(hostname=hostname, path=path):
                    response = self.client.get(path, HTTP_HOST=hostname)

                    self.assertEqual(response.status_code, 200)
                    for marker in live_analytics_markers:
                        self.assertNotContains(response, marker)

        for path in analytics_paths:
            with self.subTest(hostname="production", path=path):
                response = self.client.get(
                    path,
                    HTTP_HOST="omnilab-bk8q.onrender.com",
                )

                self.assertEqual(response.status_code, 200)
                for marker in live_analytics_markers:
                    self.assertContains(response, marker, count=1)

    @override_settings(
        ALLOWED_HOSTS=["chemistry.example.edu", "preview.example.edu"],
        OMNILAB_PUBLIC_ORIGIN="https://chemistry.example.edu",
        OMNILAB_NOINDEX=False,
    )
    def test_live_posthog_follows_an_alternate_public_origin_hostname(self):
        public_response = self.client.get(
            "/",
            HTTP_HOST="chemistry.example.edu",
        )
        preview_response = self.client.get(
            "/",
            HTTP_HOST="preview.example.edu",
        )

        self.assertContains(public_response, "posthog.init(", count=1)
        self.assertNotContains(preview_response, "posthog.init(")

    @override_settings(
        ALLOWED_HOSTS=["chemistry.example.edu"],
        OMNILAB_PUBLIC_ORIGIN="https://chemistry.example.edu",
        OMNILAB_NOINDEX=True,
    )
    def test_noindex_public_host_suppresses_live_posthog(self):
        response = self.client.get(
            "/",
            HTTP_HOST="chemistry.example.edu",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "posthog.init(")

    @override_settings(
        ALLOWED_HOSTS=["chemistry.example.edu"],
        OMNILAB_PUBLIC_ORIGIN="",
        OMNILAB_NOINDEX=False,
    )
    def test_missing_public_origin_suppresses_live_posthog(self):
        response = self.client.get(
            "/",
            HTTP_HOST="chemistry.example.edu",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "posthog.init(")

    @override_settings(
        ALLOWED_HOSTS=["chemistry.example.edu"],
        OMNILAB_PUBLIC_ORIGIN="not-an-origin",
        OMNILAB_NOINDEX=False,
    )
    def test_malformed_public_origin_suppresses_live_posthog(self):
        response = self.client.get(
            "/",
            HTTP_HOST="chemistry.example.edu",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "posthog.init(")

    def test_lab_setup_event_contains_only_coarse_setup_properties(self):
        source = "\n".join(
            (
                (
                    settings.BASE_DIR
                    / "static/ts/interactions/interactions.ts"
                ).read_text(),
                (
                    settings.BASE_DIR / "static/ts/userInterface/ui.ts"
                ).read_text(),
            )
        )
        setup_captures = re.findall(
            r"captureLabSetupStarted\(\{(.*?)\}\);",
            source,
            re.DOTALL,
        )

        self.assertEqual(len(setup_captures), 2)
        for properties in setup_captures:
            self.assertIn("vessel", properties)
            self.assertIn("burner_active", properties)

            for private_value in (
                "selectedChemicals",
                "chemical",
                "query",
                "reaction",
                "formData",
            ):
                with self.subTest(private_value=private_value):
                    self.assertNotIn(private_value, properties)

    def test_lab_setup_event_is_captured_once_per_page(self):
        analytics = (
            settings.BASE_DIR / "static/ts/analytics/analytics.ts"
        ).read_text()

        self.assertIn("if (labSetupCaptured) return;", analytics)
        self.assertIn("capture('lab_setup_started', properties);", analytics)

    def test_setup_and_completion_share_the_same_entry_attribution(self):
        analytics = (
            settings.BASE_DIR / "static/ts/analytics/analytics.ts"
        ).read_text()
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        interface = (
            settings.BASE_DIR / "static/ts/userInterface/ui.ts"
        ).read_text()

        self.assertEqual(
            interactions.count("...config.getLabEntryAttribution()"),
            2,
        )
        self.assertEqual(
            interface.count("...config.getLabEntryAttribution()"),
            1,
        )
        completed_capture = interactions.split(
            "capture('reaction_analysis_completed', {", 1
        )[1].split("});", 1)[0]
        self.assertIn("...config.getLabEntryAttribution()", completed_capture)
        self.assertNotIn("selectedChemicals:", completed_capture)

    def test_entry_attribution_has_four_bounded_privacy_safe_paths(self):
        configuration = (
            settings.BASE_DIR / "static/ts/configuration/config.ts"
        ).read_text()

        for entry_source in ("guide", "prepared_demo", "direct", "unknown"):
            with self.subTest(entry_source=entry_source):
                self.assertIn(f"entry_source: '{entry_source}'", configuration)
        self.assertIn("prepared_reaction_id: reactionDemo.id", configuration)
        self.assertNotIn("entry_source: rawSource", configuration)
        self.assertNotIn("visit_source: rawSource", configuration)

    def test_runtime_entry_uses_browser_resolvable_module_imports(self):
        entry = (settings.BASE_DIR / "static/ts/root/main.ts").read_text()

        for module_path in (
            "../configuration/config.js",
            "../userInterface/ui.js",
            "../rendering/render.js",
            "../interactions/interactions.js",
            "../analytics/analytics.js",
        ):
            with self.subTest(module_path=module_path):
                self.assertIn(f"from '{module_path}'", entry)

    def test_reaction_events_exclude_private_lab_content(self):
        source = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        captures = re.findall(
            r"capture\('reaction_analysis_(?:started|completed|failed)', \{"
            r"(.*?)\}\);",
            source,
            re.DOTALL,
        )

        self.assertEqual(len(captures), 6)
        for properties in captures:
            property_names = set(
                re.findall(r"^\s*([a-zA-Z_]+):", properties, re.MULTILINE)
            )
            for private_value in (
                "selectedChemicals",
                "query",
                "equation",
                "explanation",
                "safety",
                "formData",
            ):
                with self.subTest(private_value=private_value):
                    self.assertNotIn(private_value, property_names)

    def test_demo_entry_event_contains_only_coarse_properties(self):
        entry = (settings.BASE_DIR / "static/ts/root/main.ts").read_text()
        capture_match = re.search(
            r"capture\('reaction_demo_entered', \{(.*?)\}\);",
            entry,
            re.DOTALL,
        )

        self.assertIsNotNone(capture_match)
        properties = capture_match.group(1)
        property_names = set(
            re.findall(r"^\s*([a-zA-Z_]+):", properties, re.MULTILINE)
        )
        self.assertIn("demo_version", properties)
        self.assertIn("chemical_count", properties)
        self.assertIn("vessel", properties)
        for private_value in (
            "selectedChemicals:",
            "chemical_name",
            "query",
            "reaction",
            "equation",
            "explanation",
            "safety",
        ):
            with self.subTest(private_value=private_value):
                self.assertNotIn(private_value.rstrip(":"), property_names)

    def test_student_invitation_source_is_allowlisted_for_demo_measurement(self):
        configuration = (
            settings.BASE_DIR / "static/ts/configuration/config.ts"
        ).read_text()
        entry = (settings.BASE_DIR / "static/ts/root/main.ts").read_text()
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()

        self.assertIn(
            "export type VisitSource = 'student_invite' | GuideVisitSource;",
            configuration,
        )
        for visit_source in (
            "student_invite",
            "guide_reaction",
            "guide_formula",
            "guide_ionic_bond",
            "guide_virtual_lab",
            "guide_observation_a",
            "guide_observation_b",
            "guide_observation_c",
            "guide_observation_d",
            "guide_observation_e",
        ):
            with self.subTest(visit_source=visit_source):
                self.assertIn(f"'{visit_source}'", configuration)
        self.assertIn(
            "new URLSearchParams(window.location.search).get('source')",
            configuration,
        )
        self.assertIn("if (!getReactionDemoConfig()) return null;", configuration)
        self.assertEqual(entry.count("visit_source: visitSource"), 1)

        completed_capture = interactions.split(
            "capture('reaction_analysis_completed', {", 1
        )[1].split("});", 1)[0]
        self.assertEqual(
            completed_capture.count("...config.getLabEntryAttribution()"),
            1,
        )
        for private_value in (
            "selectedChemicals:",
            "chemical_name",
            "email",
            "query:",
            "equation",
            "explanation",
            "safety",
        ):
            with self.subTest(private_value=private_value):
                self.assertNotIn(private_value, completed_capture)

    def test_guide_entry_event_contains_only_the_fixed_source(self):
        entry = (settings.BASE_DIR / "static/ts/root/guide.ts").read_text()
        capture_match = re.search(
            r"capture\('chemistry_guide_entered', \{(.*?)\}\);",
            entry,
            re.DOTALL,
        )

        self.assertIsNotNone(capture_match)
        property_names = set(
            re.findall(
                r"(?:^|\s)([a-zA-Z_]+):",
                capture_match.group(1),
            )
        )
        self.assertEqual(property_names, {"visit_source"})
        self.assertIn("getGuideVisitSource", entry)
        for private_value in (
            "name",
            "email",
            "chemical",
            "query",
            "equation",
            "explanation",
            "safety",
            "location",
            "href",
            "pathname",
            "title",
        ):
            with self.subTest(private_value=private_value):
                self.assertNotIn(private_value, capture_match.group(1))


class ShareableReactionDemoTests(TestCase):
    def test_demo_route_prepares_supported_inputs_and_beaker(self):
        response = self.client.get("/demo/sodium-chlorine/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sodium and chlorine, ready to analyze")
        self.assertContains(response, "Na + Cl2")
        self.assertContains(
            response,
            '<button type="button" class="apparatus-option-card selected" '
            'id="opt-beaker" aria-pressed="true">Laboratory Beaker</button>',
            html=True,
        )
        self.assertContains(
            response,
            f"window.reactionDemo = {json.dumps(SODIUM_CHLORINE_DEMO)};",
        )

    def test_demo_is_shareable_without_becoming_a_search_page(self):
        response = self.client.get("/demo/sodium-chlorine/")

        self.assertContains(
            response,
            f'<link rel="canonical" href="{PUBLIC_CANONICAL_URLS["index"]}">',
            html=True,
        )
        self.assertContains(
            response,
            '<meta name="robots" content="noindex, follow">',
            html=True,
        )
        self.assertContains(
            response,
            f'<meta property="og:url" content="{SODIUM_CHLORINE_DEMO_URL}">',
            html=True,
        )
        sitemap = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn(SODIUM_CHLORINE_DEMO_URL, sitemap)

    def test_homepage_keeps_its_empty_unscripted_start(self):
        response = self.client.get("/")

        self.assertContains(
            response,
            "<title>Virtual chemistry lab for students | OmniLab</title>",
            html=True,
        )
        self.assertContains(response, "Test chemical reactions in a virtual lab")
        self.assertContains(response, "Empty Vessel")
        self.assertContains(response, "window.reactionDemo = null;")
        self.assertContains(
            response,
            "Choose a supported pair from Chemicals. Try "
            "<strong>Hydrogen and Oxygen</strong> or "
            "<strong>Hydrochloric acid and Sodium hydroxide</strong>.",
            html=True,
        )
        self.assertContains(
            response,
            '<a class="lab-demo-link" href="/demo/sodium-chlorine/">'
            ' Open the prepared Sodium and Chlorine demo '
            '<span class="lab-control-arrow" aria-hidden="true">&rarr;</span>'
            '</a>',
            html=True,
        )
        self.assertNotContains(
            response,
            '<meta name="robots" content="noindex, follow">',
            html=True,
        )
        self.assertNotContains(response, 'name="robots"')

    def test_default_instruction_keeps_demo_link_after_normal_lab_reset(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        default_instruction = interactions.split(
            "const DEFAULT_REACTION_INSTRUCTION =", 1
        )[1].split("const DEMO_REACTION_INSTRUCTION =", 1)[0]

        self.assertIn("Sodium and Chlorine", default_instruction)
        self.assertIn('href="/demo/sodium-chlorine/"', default_instruction)
        self.assertIn(
            '<span class="lab-control-arrow" aria-hidden="true">&rarr;</span>',
            default_instruction,
        )
        self.assertNotIn("window.reactionDemo", default_instruction)

    def test_lab_pages_do_not_request_unused_icon_or_three_dimensional_assets(self):
        for path in ("/", "/demo/sodium-chlorine/"):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    "bootstrap@5.3.0/dist/css/bootstrap.min.css",
                )
                self.assertNotContains(response, "bootstrap-icons")
                self.assertNotContains(response, "three.min.js")
                self.assertNotContains(response, "cdnjs.cloudflare.com/ajax/libs/three")

    def test_demo_uses_isolated_storage_and_never_auto_submits(self):
        configuration = (
            settings.BASE_DIR / "static/ts/configuration/config.ts"
        ).read_text()
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        entry = (settings.BASE_DIR / "static/ts/root/main.ts").read_text()

        self.assertIn("reactionDemo:${reactionDemo.id}:${baseKey}", configuration)
        for key in ("savedChemicals", "savedLiquidColor", "savedReaction"):
            with self.subTest(key=key):
                self.assertIn(f"config.getLabStorageKey('{key}')", interactions)
        self.assertIn(
            "analyzeBtn.addEventListener('click', interactions.fireAIAnalysis)",
            entry,
        )
        demo_initialization = interactions.split(
            'document.addEventListener("DOMContentLoaded", () => {', 1
        )[1]
        self.assertNotIn("fireAIAnalysis", demo_initialization)


class PredictionInputClarityTests(TestCase):
    def test_normal_lab_and_demo_explain_prediction_inputs_before_analysis(self):
        for path in ("/", "/demo/sodium-chlorine/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                html = response.content.decode()

                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    "Selected chemicals only. Vessel and burner choices are "
                    "visual setup aids.",
                )
                self.assertContains(
                    response,
                    'aria-describedby="prediction-input-note"',
                )
                self.assertLess(
                    html.index('id="prediction-input-note"'),
                    html.index('id="btn-fire-analysis"'),
                )


class AccessibleLabSetupTests(TestCase):
    def test_apparatus_choices_are_native_pressed_buttons(self):
        normal_html = self.client.get("/").content.decode()
        demo_html = self.client.get("/demo/sodium-chlorine/").content.decode()

        for html in (normal_html, demo_html):
            with self.subTest(path="normal" if html is normal_html else "demo"):
                self.assertIn('role="group" aria-label="Choose lab apparatus"', html)
                for option_id in ("flask", "tube", "beaker", "burner"):
                    self.assertIn(
                        f'<button type="button" class="apparatus-option-card',
                        html,
                    )
                    self.assertIn(f'id="opt-{option_id}" aria-pressed=', html)

        self.assertIn('id="opt-flask" aria-pressed="true"', normal_html)
        self.assertIn('id="opt-beaker" aria-pressed="true"', demo_html)

    def test_chemical_buttons_share_one_pointer_keyboard_and_drag_path(self):
        ui = (settings.BASE_DIR / "static/ts/userInterface/ui.ts").read_text()
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        entry = (settings.BASE_DIR / "static/ts/root/main.ts").read_text()

        self.assertIn("document.createElement('button')", ui)
        self.assertIn("card.type = 'button'", ui)
        self.assertIn("card.setAttribute('draggable', 'true')", ui)
        self.assertIn("card.setAttribute('aria-label'", ui)
        self.assertIn("card.setAttribute(\n            'aria-pressed'", ui)
        self.assertIn("card.addEventListener('click'", ui)
        self.assertIn("onSelectChemical(chem.id, chem.color)", ui)
        self.assertIn("ev.currentTarget", ui)
        self.assertIn("ui.buildChemicalMenu((name: string, color: string)", entry)
        self.assertIn("interactions.addChemicalToLab(name, color)", entry)

        add_block = interactions.split(
            "export function addChemicalToLab(", 1
        )[1].split("\n}\n\nexport function drop", 1)[0]
        drop_block = interactions.split(
            "export function drop(ev: DragEvent): void {", 1
        )[1].split("\n}\n\nexport function resetLaboratory", 1)[0]
        self.assertEqual(add_block.count("captureLabSetupStarted({"), 1)
        self.assertIn("updateAnalysisAvailability()", add_block)
        self.assertIn("addChemicalToLab(name, color", drop_block)

    def test_setup_controls_expose_state_focus_and_touch_targets(self):
        html = self.client.get("/").content.decode()
        ui = (settings.BASE_DIR / "static/ts/userInterface/ui.ts").read_text()
        css = (settings.BASE_DIR / "static/css/style.css").read_text()

        self.assertIn('aria-controls="sub-panel-chemicals"', html)
        self.assertIn('aria-controls="sub-panel-apparatus"', html)
        self.assertEqual(html.count('aria-expanded="false"'), 2)
        self.assertIn("trigger.setAttribute('aria-expanded', 'true')", ui)
        self.assertIn("b.setAttribute('aria-expanded', 'false')", ui)
        self.assertIn("option?.focus()", ui)
        self.assertIn(".chemical-card:focus-visible", css)
        self.assertIn(".apparatus-option-card:focus-visible", css)
        self.assertGreaterEqual(css.count("min-height: 44px"), 2)


class SupportedSetupAnalysisStateTests(TestCase):
    def test_first_experiment_starts_empty_and_guides_the_supported_path(self):
        response = self.client.get("/first-experiment/")
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<meta name="robots" content="noindex, follow">',
            html=True,
        )
        self.assertContains(response, "OmniLab first experiment")
        self.assertContains(response, "Step 1 of 4")
        self.assertContains(response, "Add sodium")
        self.assertContains(response, "Empty Vessel")
        self.assertContains(response, "window.firstExperiment = true;")
        self.assertContains(response, 'href="/">Use the open lab instead</a>')
        self.assertNotContains(response, "Twenty-eight chemistry guides")
        button = html.split('id="btn-fire-analysis"', 1)[1].split(">", 1)[0]
        self.assertIn("disabled", button)

    def test_first_experiment_preserves_focus_and_touch_targets(self):
        css = (settings.BASE_DIR / "static/css/style.css").read_text()
        entry = (settings.BASE_DIR / "static/ts/root/main.ts").read_text()
        guide = (
            settings.BASE_DIR
            / "static/ts/firstExperiment/firstExperiment.ts"
        ).read_text()

        toolbar_block = css.split(".toolbar-trigger-btn {", 1)[1].split("}", 1)[0]
        reset_block = css.split("#btn-reset-lab {", 1)[1].split("}", 1)[0]
        reset_focus_block = css.split(
            "#btn-reset-lab:focus-visible {", 1
        )[1].split("}", 1)[0]

        self.assertIn("min-height: 44px", toolbar_block)
        self.assertIn("min-height: 44px", reset_block)
        self.assertIn("min-width: 44px", reset_block)
        self.assertIn("outline: 3px solid #e3384f", reset_focus_block)
        self.assertIn("targetForStep(step)?.focus()", guide)
        self.assertGreaterEqual(
            entry.count("firstExperiment.advanceFirstExperimentGuide()"),
            3,
        )

    def test_first_experiment_uses_isolated_browser_storage(self):
        configuration = (
            settings.BASE_DIR / "static/ts/configuration/config.ts"
        ).read_text()

        self.assertIn("window.firstExperiment", configuration)
        self.assertIn("`firstExperiment:v1:${baseKey}`", configuration)

    def test_normal_lab_starts_disabled_with_missing_input_guidance(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Add two chemicals from a supported reaction pair.",
        )
        self.assertContains(
            response,
            'id="btn-fire-analysis" aria-describedby="prediction-input-note" disabled',
        )

    def test_prepared_demo_starts_ready_to_analyze(self):
        response = self.client.get("/demo/sodium-chlorine/")
        html = response.content.decode()
        button = html.split('id="btn-fire-analysis"', 1)[1].split(">", 1)[0]

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Ready to analyze this supported reaction pair.",
        )
        self.assertNotIn("disabled", button)

    def test_browser_uses_one_exact_order_independent_support_rule(self):
        configuration = (
            settings.BASE_DIR / "static/ts/configuration/config.ts"
        ).read_text()
        support_rule = configuration.split(
            "export function isSupportedReactionSetup", 1
        )[1].split("\n}\n", 1)[0]

        self.assertIn("supportedReactionPairKeys", configuration)
        self.assertIn("selectedChemicals.length !== 2", support_rule)
        self.assertIn("[...selectedChemicals].sort().join('+')", support_rule)
        self.assertIn("supportedReactionPairKeys.has", support_rule)

    def test_catalog_marks_compatible_partners_from_the_server_pair_list(self):
        response = self.client.get("/")
        configuration = (
            settings.BASE_DIR / "static/ts/configuration/config.ts"
        ).read_text()
        ui = (
            settings.BASE_DIR / "static/ts/userInterface/ui.ts"
        ).read_text()
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        add_block = interactions.split(
            "export function addChemicalToLab(", 1
        )[1].split("\n}\n\nexport function drop", 1)[0]

        self.assertContains(response, 'id="chemical-partner-guidance"')
        self.assertContains(response, 'aria-live="polite"')
        self.assertIn("supportedReactionPartners", configuration)
        self.assertIn("getCompatibleReactionPartners", configuration)
        self.assertIn("compatible-partner", ui)
        self.assertIn("Compatible with ${selectedName}", ui)
        self.assertIn("refreshChemicalMenuGuidance();", ui)
        self.assertIn("refreshChemicalMenuGuidance();", add_block)
        self.assertLess(
            add_block.index("refreshChemicalMenuGuidance();"),
            add_block.index("updateAnalysisAvailability();"),
        )

    def test_unsupported_pair_guidance_is_specific_and_honest(self):
        ui = (
            settings.BASE_DIR / "static/ts/userInterface/ui.ts"
        ).read_text()
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()

        self.assertIn("isn't in OmniLab's supported set", ui)
        self.assertIn("doesn't mean the combination is chemically impossible", ui)
        self.assertIn("not supported in OmniLab", interactions)
        self.assertIn("marked compatible pair", interactions)

    def test_disabled_setup_stops_before_analytics_and_network(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        analysis_block = interactions.split(
            "export function fireAIAnalysis(): void {", 1
        )[1].split('\n}\n\ndocument.addEventListener("DOMContentLoaded"', 1)[0]

        support_guard = analysis_block.index(
            "if (!config.isSupportedReactionSetup(state.selectedChemicals))"
        )
        capture_position = analysis_block.index(
            "capture('reaction_analysis_started'"
        )
        fetch_position = analysis_block.index("fetch('/ai_insights/'")

        self.assertLess(support_guard, capture_position)
        self.assertLess(support_guard, fetch_position)

    def test_drop_demo_reset_and_request_exit_refresh_button_state(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        add_block = interactions.split(
            "export function addChemicalToLab(", 1
        )[1].split("\n}\n\nexport function drop", 1)[0]
        drop_block = interactions.split(
            "export function drop(ev: DragEvent): void {", 1
        )[1].split("\n}\n\nexport function resetLaboratory", 1)[0]
        reset_block = interactions.split(
            "export function resetLaboratory(): void {", 1
        )[1].split("\n}\n\nfunction getCsrfToken", 1)[0]
        initialization_block = interactions.split(
            'document.addEventListener("DOMContentLoaded", () => {', 1
        )[1]

        self.assertIn("addChemicalToLab(name, color", drop_block)
        self.assertIn("updateAnalysisAvailability()", add_block)
        self.assertIn("selectedChemicals: []", reset_block)
        self.assertIn("setAnalysisPending(false)", reset_block)
        self.assertLess(
            reset_block.index("selectedChemicals: []"),
            reset_block.index("setAnalysisPending(false)"),
        )
        self.assertIn("updateAnalysisAvailability()", initialization_block)


class SavedChemicalRestorationTests(TestCase):
    def setUp(self):
        self.configuration = (
            settings.BASE_DIR / "static/ts/configuration/config.ts"
        ).read_text()
        self.interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        self.restore_block = self.interactions.split(
            'document.addEventListener("DOMContentLoaded", () => {', 1
        )[1]

    def test_saved_chemicals_use_one_safe_parser(self):
        parser = self.configuration.split(
            "export function parseSavedChemicals", 1
        )[1].split("\n}\n", 1)[0]

        self.assertIn("try {", parser)
        self.assertIn("JSON.parse(serializedChemicals)", parser)
        self.assertIn("Array.isArray(parsedChemicals)", parser)
        self.assertIn("supportedChemicalIds.has(chemical)", parser)
        self.assertIn(
            "new Set(parsedChemicals).size !== parsedChemicals.length",
            parser,
        )
        self.assertIn("catch {", parser)
        self.assertNotIn("JSON.parse(savedChemicals)", self.restore_block)
        self.assertIn(
            "config.parseSavedChemicals(storedChemicals)",
            self.restore_block,
        )

    def test_invalid_storage_is_removed_before_initial_state_is_applied(self):
        invalid_guard = (
            "if (storedChemicals !== null && savedChemicals === null) {"
        )
        remove_invalid = "removeStorageValue(chemicalsStorageKey);"
        prepared_state = "const preparedChemicals = savedChemicals"

        self.assertIn(invalid_guard, self.restore_block)
        self.assertIn(remove_invalid, self.restore_block)
        self.assertLess(
            self.restore_block.index(invalid_guard),
            self.restore_block.index(prepared_state),
        )

    def test_valid_empty_and_populated_saved_arrays_override_defaults(self):
        self.assertIn(
            "const preparedChemicals = savedChemicals\n"
            "        ?? reactionDemo?.selectedChemicals\n"
            "        ?? [];",
            self.restore_block,
        )
        self.assertNotIn("savedChemicals ||", self.restore_block)
        self.assertNotIn("savedChemicals ?", self.restore_block)

    def test_prepared_demo_fills_only_when_saved_state_is_absent_or_invalid(self):
        fallback_guard = "if (savedChemicals === null && reactionDemo) {"

        self.assertIn(fallback_guard, self.restore_block)
        fallback_block = self.restore_block.split(fallback_guard, 1)[1].split(
            "\n    }", 1
        )[0]
        self.assertIn(
            "JSON.stringify(reactionDemo.selectedChemicals)",
            fallback_block,
        )
        self.assertIn(
            "writeStorageValue(liquidColorStorageKey, reactionDemo.liquidColor)",
            fallback_block,
        )

    def test_result_color_and_reset_cleanup_contracts_remain_in_place(self):
        self.assertIn(
            "removeStorageValue(liquidColorStorageKey);",
            self.restore_block,
        )
        self.assertIn(
            "removeStorageValue(reactionStorageKey);",
            self.restore_block,
        )
        reset_block = self.interactions.split(
            "export function resetLaboratory(): void {", 1
        )[1].split("\n}\n\nfunction getCsrfToken", 1)[0]
        for storage_name in (
            "savedChemicals",
            "savedLiquidColor",
            "savedReaction",
        ):
            self.assertIn(
                f"removeStorageValue(config.getLabStorageKey('{storage_name}'))",
                reset_block,
            )


class OptionalBrowserStorageTests(TestCase):
    def setUp(self):
        self.storage = (
            settings.BASE_DIR / "static/ts/storage/storage.ts"
        ).read_text()
        self.interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()

    def test_storage_helpers_turn_browser_failures_into_safe_defaults(self):
        self.assertIn("return window.localStorage.getItem(key);", self.storage)
        self.assertIn("window.localStorage.setItem(key, value);", self.storage)
        self.assertIn("window.localStorage.removeItem(key);", self.storage)
        self.assertEqual(self.storage.count("try {"), 3)
        self.assertEqual(self.storage.count("catch {"), 3)
        self.assertIn("return null;", self.storage)

    def test_lab_routes_every_storage_operation_through_safe_helpers(self):
        self.assertIn("from '../storage/storage.js';", self.interactions)
        self.assertIn("readStorageValue(chemicalsStorageKey)", self.interactions)
        self.assertIn("readStorageValue(reactionStorageKey)", self.interactions)
        self.assertIn("writeStorageValue(", self.interactions)
        self.assertIn("removeStorageValue(", self.interactions)
        self.assertNotIn("localStorage.", self.interactions)


@override_settings(
    OMNILAB_REACTION_RATE_LIMIT_REQUESTS=2,
    OMNILAB_REACTION_RATE_LIMIT_WINDOW_SECONDS=60,
)
class ReactionRateLimitTests(TestCase):
    def setUp(self):
        self.rate_limit_directory = tempfile.TemporaryDirectory()
        self.rate_limit_database = (
            Path(self.rate_limit_directory.name) / "rate-limits.sqlite3"
        )
        self.rate_limit_settings = self.settings(
            OMNILAB_REACTION_RATE_LIMIT_DATABASE_PATH=(
                self.rate_limit_database
            )
        )
        self.rate_limit_settings.enable()

    def tearDown(self):
        self.rate_limit_settings.disable()
        self.rate_limit_directory.cleanup()

    def post_reaction(
        self,
        forwarded_for="203.0.113.10",
        remote_addr="127.0.0.1",
    ):
        request_headers = {"REMOTE_ADDR": remote_addr}
        if forwarded_for is not None:
            request_headers["HTTP_X_FORWARDED_FOR"] = forwarded_for
        return self.client.post(
            "/ai_insights/", {"query": "Na + Cl2"}, **request_headers
        )

    def test_normal_reaction_request_returns_matrix_result(self):
        with patch("omnilab.views.time.time", return_value=1200):
            response = self.post_reaction()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(
            response.json()["data"]["equation"],
            "2Na(s) + Cl2(g) -> 2NaCl(s)",
        )

    def test_exceeded_limit_returns_retry_guidance(self):
        with patch("omnilab.views.time.time", return_value=1200):
            self.assertEqual(self.post_reaction().status_code, 200)
            self.assertEqual(self.post_reaction().status_code, 200)
            response = self.post_reaction()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["status"], "rate_limited")
        self.assertIn("Try again in 60 seconds", response.json()["message"])
        self.assertEqual(response.headers["Retry-After"], "60")

    def test_separate_processes_share_one_limit(self):
        process_context = multiprocessing.get_context("fork")
        result_queue = process_context.Queue()
        client_digest = hashlib.sha256(b"203.0.113.10").hexdigest()
        processes = [
            process_context.Process(
                target=_increment_reaction_limit_in_process,
                args=(
                    self.rate_limit_database,
                    client_digest,
                    20,
                    result_queue,
                ),
            )
            for _ in range(2)
        ]

        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=10)
            self.assertEqual(process.exitcode, 0)

        self.assertCountEqual(
            [result_queue.get(timeout=1) for _ in processes],
            [1, 2],
        )
        with patch("omnilab.views.time.time", return_value=1200):
            response = self.post_reaction()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["status"], "rate_limited")

    @override_settings(OMNILAB_REACTION_RATE_LIMIT_REQUESTS=1)
    def test_reaction_request_recovers_after_window(self):
        with patch("omnilab.views.time.time", return_value=1200):
            self.assertEqual(self.post_reaction().status_code, 200)
            self.assertEqual(self.post_reaction().status_code, 429)

        with patch("omnilab.views.time.time", return_value=1260):
            response = self.post_reaction()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

    @override_settings(OMNILAB_REACTION_RATE_LIMIT_REQUESTS=1)
    def test_appended_forwarded_hops_cannot_rotate_client_key(self):
        with patch("omnilab.views.time.time", return_value=1200):
            first_response = self.post_reaction(
                forwarded_for="203.0.113.10, 198.51.100.20"
            )
            blocked_response = self.post_reaction(
                forwarded_for="203.0.113.10, 192.0.2.30"
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(blocked_response.status_code, 429)

    @override_settings(OMNILAB_REACTION_RATE_LIMIT_REQUESTS=1)
    def test_malformed_forwarded_address_uses_socket_fallback(self):
        with patch("omnilab.views.time.time", return_value=1200):
            first_response = self.post_reaction(
                forwarded_for="not-an-address",
                remote_addr="198.51.100.40",
            )
            blocked_response = self.post_reaction(
                forwarded_for="still-not-an-address",
                remote_addr="198.51.100.40",
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(blocked_response.status_code, 429)


class SupportedReactionBoundaryTests(TestCase):
    rejection_cases = (
        ("missing", ""),
        ("single input", "Na"),
        ("duplicate input", "Na + Na"),
        ("unknown input", "Na + Xe"),
        ("unknown pair", "Cu + H2O"),
        ("additional input", "Na + Cl2 + H2O"),
    )

    @patch("omnilab.views.reaction_rate_limit")
    def test_rejected_setups_do_not_reach_throttle(
        self, reaction_rate_limit
    ):
        for label, query in self.rejection_cases:
            with self.subTest(label=label, query=query):
                reaction_rate_limit.reset_mock()

                response = self.client.post(
                    "/ai_insights/", {"query": query}
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json(),
                    {
                        "status": "insufficient_input",
                        "message": (
                            "Choose two chemicals from a supported reaction "
                            "pair, then try again."
                        ),
                    },
                )
                reaction_rate_limit.assert_not_called()

    @patch("omnilab.views.reaction_rate_limit", return_value=None)
    def test_both_supported_orders_return_the_same_matrix_result(
        self, reaction_rate_limit
    ):
        for query in ("Na + Cl2", "Cl2 + Na"):
            with self.subTest(query=query):
                reaction_rate_limit.reset_mock()

                response = self.client.post(
                    "/ai_insights/", {"query": query}
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "success")
                reaction_rate_limit.assert_called_once()


class DeterministicReactionMatrixTests(TestCase):
    requested_chemical_ids = {
        "H2",
        "O2",
        "H2O",
        "C",
        "CO2",
        "HCl",
        "NaOH",
        "NaCl",
        "Fe",
        "Cu",
        "NH3",
        "H2SO4",
        "HNO3",
        "CH3COOH",
        "KOH",
        "Ca(OH)2",
        "CuSO4",
        "AgNO3",
        "KI",
        "KMnO4",
        "Na2CO3",
        "NaHCO3",
        "BaCl2",
        "H2O2",
        "Zn",
        "HF",
        "HBr",
        "HI",
        "AgCl",
        "AlCl3",
        "MgSO4",
        "HgCl2",
        "CO",
        "NO2",
        "H2S",
        "O3",
    }

    def test_catalog_contains_all_requested_substances_once(self):
        catalog = json.loads(
            (settings.BASE_DIR / "static/js/chemicaldata.json").read_text()
        )
        catalog_ids = [chemical["id"] for chemical in catalog]

        self.assertTrue(self.requested_chemical_ids.issubset(catalog_ids))
        self.assertEqual(len(catalog_ids), len(set(catalog_ids)))
        self.assertEqual(len(catalog_ids), 38)
        self.assertEqual(set(catalog_ids), set(SUPPORTED_CHEMICAL_IDS))

    def test_matrix_preserves_existing_pair_and_required_reactions(self):
        expected_equations = {
            frozenset({"Na", "Cl2"}): "2Na(s) + Cl2(g) -> 2NaCl(s)",
            frozenset({"H2", "O2"}): "2H2(g) + O2(g) -> 2H2O(l)",
            frozenset({"HCl", "NaOH"}): (
                "HCl(aq) + NaOH(aq) -> NaCl(aq) + H2O(l)"
            ),
            frozenset({"NH3", "HNO3"}): (
                "NH3(aq) + HNO3(aq) -> NH4NO3(aq)"
            ),
            frozenset({"H2SO4", "KOH"}): (
                "H2SO4(aq) + 2KOH(aq) -> K2SO4(aq) + 2H2O(l)"
            ),
            frozenset({"CH3COOH", "NaHCO3"}): (
                "CH3COOH(aq) + NaHCO3(s) -> "
                "CH3COONa(aq) + CO2(g) + H2O(l)"
            ),
            frozenset({"Ca(OH)2", "CO2"}): (
                "Ca(OH)2(aq) + CO2(g) -> CaCO3(s) + H2O(l)"
            ),
            frozenset({"CuSO4", "KOH"}): (
                "CuSO4(aq) + 2KOH(aq) -> Cu(OH)2(s) + K2SO4(aq)"
            ),
            frozenset({"AgNO3", "NaCl"}): (
                "AgNO3(aq) + NaCl(aq) -> AgCl(s) + NaNO3(aq)"
            ),
            frozenset({"AgNO3", "KI"}): (
                "AgNO3(aq) + KI(aq) -> AgI(s) + KNO3(aq)"
            ),
            frozenset({"KMnO4", "H2O2"}): (
                "2KMnO4(aq) + 3H2O2(aq) -> "
                "2MnO2(s) + 3O2(g) + 2KOH(aq) + 2H2O(l)"
            ),
            frozenset({"Na2CO3", "HCl"}): (
                "Na2CO3(aq) + 2HCl(aq) -> "
                "2NaCl(aq) + CO2(g) + H2O(l)"
            ),
            frozenset({"BaCl2", "Na2CO3"}): (
                "BaCl2(aq) + Na2CO3(aq) -> BaCO3(s) + 2NaCl(aq)"
            ),
            frozenset({"Zn", "HCl"}): (
                "Zn(s) + 2HCl(aq) -> ZnCl2(aq) + H2(g)"
            ),
            frozenset({"HF", "NaOH"}): (
                "HF(aq) + NaOH(aq) -> NaF(aq) + H2O(l)"
            ),
            frozenset({"HBr", "NaOH"}): (
                "HBr(aq) + NaOH(aq) -> NaBr(aq) + H2O(l)"
            ),
            frozenset({"HI", "NaOH"}): (
                "HI(aq) + NaOH(aq) -> NaI(aq) + H2O(l)"
            ),
            frozenset({"AgCl", "NH3"}): (
                "AgCl(s) + 2NH3(aq) -> [Ag(NH3)2]+(aq) + Cl-(aq)"
            ),
            frozenset({"AlCl3", "NaOH"}): (
                "AlCl3(aq) + 3NaOH(aq) -> Al(OH)3(s) + 3NaCl(aq)"
            ),
            frozenset({"MgSO4", "NaOH"}): (
                "MgSO4(aq) + 2NaOH(aq) -> Mg(OH)2(s) + Na2SO4(aq)"
            ),
            frozenset({"HgCl2", "NaOH"}): (
                "HgCl2(aq) + 2NaOH(aq) -> "
                "HgO(s) + 2NaCl(aq) + H2O(l)"
            ),
            frozenset({"CO", "O2"}): (
                "2CO(g) + O2(g) -> 2CO2(g)"
            ),
            frozenset({"NO2", "H2O"}): (
                "2NO2(g) + H2O(l) -> HNO2(aq) + HNO3(aq)"
            ),
            frozenset({"H2S", "NaOH"}): (
                "H2S(g) + 2NaOH(aq) -> Na2S(aq) + 2H2O(l)"
            ),
            frozenset({"O3", "H2O2"}): (
                "O3(g) + H2O2(aq) -> 2O2(g) + H2O(l)"
            ),
        }

        for pair, equation in expected_equations.items():
            with self.subTest(pair=pair):
                self.assertEqual(REACTION_MATRIX[pair]["equation"], equation)

    def test_every_matrix_entry_has_a_complete_safe_contract(self):
        self.assertEqual(len(REACTION_MATRIX), 34)

        for pair, reaction in REACTION_MATRIX.items():
            with self.subTest(pair=pair):
                self.assertEqual(len(pair), 2)
                self.assertTrue(pair.issubset(SUPPORTED_CHEMICAL_IDS))
                self.assertIn(
                    reaction["effect"],
                    {"explosion", "bubble", "precipitate", "none"},
                )
                self.assertTrue(reaction["explanation"].strip())
                self.assertEqual(len(reaction["safety"].split("|")), 3)
                self.assertTrue(
                    equation_uses_only_selected_reactants(
                        reaction["equation"], list(pair)
                    )
                )

    def test_eight_precipitation_reactions_have_bounded_colors(self):
        expected_precipitates = {
            frozenset({"Ca(OH)2", "CO2"}): "#f5f3ea",
            frozenset({"CuSO4", "KOH"}): "#5ba7d1",
            frozenset({"AgNO3", "NaCl"}): "#f5f3ea",
            frozenset({"AgNO3", "KI"}): "#f2c94c",
            frozenset({"BaCl2", "Na2CO3"}): "#f5f3ea",
            frozenset({"AlCl3", "NaOH"}): "#f5f3ea",
            frozenset({"MgSO4", "NaOH"}): "#f5f3ea",
            frozenset({"HgCl2", "NaOH"}): "#f2c94c",
        }

        precipitate_reactions = {
            pair: reaction
            for pair, reaction in REACTION_MATRIX.items()
            if reaction["effect"] == "precipitate"
        }
        self.assertEqual(set(precipitate_reactions), set(expected_precipitates))
        for pair, expected_color in expected_precipitates.items():
            with self.subTest(pair=pair):
                reaction = precipitate_reactions[pair]
                self.assertEqual(reaction["precipitate_color"], expected_color)
                self.assertIn(reaction["precipitate_color"], PRECIPITATE_COLORS)

    def test_precipitate_contract_rejects_missing_or_unknown_colors(self):
        valid_reaction = REACTION_MATRIX[frozenset({"AgNO3", "KI"})]

        for color in (None, "yellow", "#ffffff", 2, []):
            with self.subTest(color=color):
                candidate = {**valid_reaction, "precipitate_color": color}
                self.assertIsNone(
                    validate_complete_reaction_response(
                        candidate,
                        ["AgNO3", "KI"],
                    )
                )

    def test_non_precipitate_contract_rejects_precipitate_metadata(self):
        reaction = {
            **REACTION_MATRIX[frozenset({"Na", "Cl2"})],
            "precipitate_color": "#f5f3ea",
        }

        self.assertIsNone(
            validate_complete_reaction_response(reaction, ["Na", "Cl2"])
        )

    @patch("omnilab.views.reaction_rate_limit", return_value=None)
    def test_every_matrix_pair_is_order_independent_at_the_endpoint(
        self, _reaction_rate_limit
    ):
        for first, second in supported_reaction_pairs():
            with self.subTest(pair=(first, second)):
                forward = self.client.post(
                    "/ai_insights/", {"query": f"{first} + {second}"}
                )
                reverse = self.client.post(
                    "/ai_insights/", {"query": f"{second} + {first}"}
                )

                self.assertEqual(forward.status_code, 200)
                self.assertEqual(reverse.status_code, 200)
                self.assertEqual(forward.json(), reverse.json())

    def test_matrix_lookup_returns_defensive_copies(self):
        first = get_reaction(["H2", "O2"])
        second = get_reaction(["O2", "H2"])

        first["equation"] = "changed"
        self.assertEqual(second["equation"], "2H2(g) + O2(g) -> 2H2O(l)")


class ReactionCsrfProtectionTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def post_reaction(self, token=None, origin="https://testserver"):
        headers = {"HTTP_ORIGIN": origin}
        if token is not None:
            headers["HTTP_X_CSRFTOKEN"] = token
        return self.client.post(
            "/ai_insights/",
            {"query": "Na + Cl2"},
            secure=True,
            **headers,
        )

    def get_token(self, path="/"):
        response = self.client.get(path, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)
        return response.cookies["csrftoken"].value

    def test_tokenless_request_is_rejected(self):
        response = self.post_reaction()

        self.assertEqual(response.status_code, 403)

    def test_invalid_token_is_rejected(self):
        self.get_token()

        response = self.post_reaction("a" * 32)

        self.assertEqual(response.status_code, 403)

    def test_forged_cross_site_request_is_rejected(self):
        token = self.get_token()

        response = self.post_reaction(token, origin="https://example.net")

        self.assertEqual(response.status_code, 403)

    def test_legitimate_same_origin_request_keeps_reaction_contract(self):
        token = self.get_token()

        response = self.post_reaction(token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(
            response.json()["data"]["equation"],
            "2Na(s) + Cl2(g) -> 2NaCl(s)",
        )

    def test_demo_page_sets_token_for_the_same_browser_client(self):
        token = self.get_token("/demo/sodium-chlorine/")

        response = self.post_reaction(token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

    def test_browser_client_sends_same_origin_token(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()

        self.assertIn("'X-CSRFToken': getCsrfToken()", interactions)
        self.assertIn("credentials: 'same-origin'", interactions)


class LabJourneyRepairTests(TestCase):
    def test_catalog_exposes_the_supported_reaction_substances(self):
        catalog = json.loads(
            (settings.BASE_DIR / "static/js/chemicaldata.json").read_text()
        )

        self.assertEqual(len(catalog), 38)
        self.assertEqual(len({chemical["id"] for chemical in catalog}), 38)
        self.assertTrue(
            {"Na", "Cl2", "H2", "O2", "HCl", "NaOH", "Fe", "Cu"}
            .issubset(chemical["id"] for chemical in catalog)
        )

    def test_homepage_and_runtime_use_the_same_canvas_identifier(self):
        response = self.client.get("/")
        runtime = (
            settings.BASE_DIR / "static/ts/configuration/config.ts"
        ).read_text()

        self.assertContains(
            response,
            '<canvas id="lab-canvas"></canvas>',
            html=True,
        )
        self.assertIn("getElementById('lab-canvas')", runtime)

    def test_runtime_initializes_catalog_canvas_and_drop_path(self):
        entry = (settings.BASE_DIR / "static/ts/root/main.ts").read_text()
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        renderer = (
            settings.BASE_DIR / "static/ts/rendering/render.ts"
        ).read_text()

        for expected in (
            "fetch(jsonUrl)",
            "ui.resizeCanvas()",
            "requestAnimationFrame(engineLoop)",
            "addEventListener('drop'",
        ):
            self.assertIn(expected, entry)
        self.assertIn("selectedChemicals: updatedChemicals", interactions)
        self.assertIn("updatedChemicals.join(' + ')", interactions)
        self.assertIn("updatedState.currentVessel", renderer)
        self.assertIn("updatedState.burnerActive", renderer)

    def test_browser_submits_catalog_ids_as_selected_reactants(self):
        catalog = json.loads(
            (settings.BASE_DIR / "static/js/chemicaldata.json").read_text()
        )
        menu = (
            settings.BASE_DIR / "static/ts/userInterface/ui.ts"
        ).read_text()
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()

        self.assertEqual(len(catalog), 38)
        self.assertIn(
            ("HCl", "Hydrochloric acid"),
            [(chemical["id"], chemical["name"]) for chemical in catalog],
        )
        self.assertIn("card.setAttribute('data-name', chem.id)", menu)
        self.assertIn("state.selectedChemicals.join(' + ')", interactions)

    def test_reactant_validation_normalizes_coefficients_and_states(self):
        self.assertTrue(
            equation_uses_only_selected_reactants(
                "2Na(s) + Cl2(g) -> 2NaCl(s)", ["Na", "Cl2"]
            )
        )
        self.assertFalse(
            equation_uses_only_selected_reactants(
                "2Na(s) + 2H2O(l) -> 2NaOH(aq) + H2(g)",
                ["Na", "Cl2"],
            )
        )

    def test_instruction_text_uses_contrast_token_without_opacity(self):
        response = self.client.get("/")
        css = (settings.BASE_DIR / "static/css/style.css").read_text()
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()

        self.assertContains(response, "lab-instruction")
        self.assertIn(".lab-instruction", css)
        self.assertIn("color: var(--muted-text);", css)
        self.assertNotIn('style="opacity: 0.6;"', interactions)

    def test_reaction_results_keep_heading_order_and_safety_contrast(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        css = (settings.BASE_DIR / "static/css/style.css").read_text()
        render_block = interactions.split(
            "export function renderReactionResult", 1
        )[1].split("\n}\n\nfunction renderStatusMessage", 1)[0]

        self.assertNotIn("<h6", interactions)
        equation_heading = render_block.index("Chemical Equation Formula")
        analysis_heading = render_block.index("Analysis")
        safety_heading = render_block.index("Safety rules")
        self.assertLess(equation_heading, analysis_heading)
        self.assertLess(analysis_heading, safety_heading)
        self.assertIn("safety-heading", interactions)
        self.assertIn("safety-list", interactions)
        self.assertIn(".safety-heading", css)
        self.assertIn(".safety-list", css)
        self.assertIn("color: var(--text-color);", css)

    def test_reaction_result_marks_do_not_require_an_icon_font(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        css = (settings.BASE_DIR / "static/css/style.css").read_text()
        render_block = interactions.split(
            "export function renderReactionResult", 1
        )[1].split("\n}\n\nfunction renderStatusMessage", 1)[0]

        self.assertNotIn('class="bi ', interactions)
        self.assertNotIn("document.createElement('i')", interactions)
        self.assertEqual(render_block.count('class="result-heading-mark'), 3)
        self.assertIn(
            '<span class="lab-control-arrow" aria-hidden="true">&nearr;</span>',
            render_block,
        )
        self.assertIn("document.createElement('span')", render_block)
        self.assertIn("icon.className = 'safety-rule-mark me-2'", render_block)
        self.assertIn("icon.textContent = '!'", render_block)
        self.assertIn(".result-heading-mark", css)
        self.assertIn(".safety-rule-mark", css)

    def test_reaction_results_render_matrix_fields_as_text(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        render_block = interactions.split(
            "export function renderReactionResult", 1
        )[1].split("\n}\n\nfunction renderStatusMessage", 1)[0]

        self.assertIn("equation.textContent = reaction.equation", render_block)
        self.assertIn(
            "explanation.textContent = reaction.explanation", render_block
        )
        self.assertIn("document.createTextNode(point)", render_block)
        self.assertNotIn("${reaction.equation}", render_block)
        self.assertNotIn("${reaction.explanation}", render_block)
        self.assertNotIn("${reaction.safety}", render_block)

    def test_successful_result_offers_optional_in_page_feedback(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        feedback = (
            settings.BASE_DIR / "static/ts/interactions/feedback.ts"
        ).read_text()
        css = (settings.BASE_DIR / "static/css/style.css").read_text()
        render_block = interactions.split(
            "export function renderReactionResult", 1
        )[1].split("\n}\n\nfunction renderStatusMessage", 1)[0]
        status_block = interactions.split(
            "function renderStatusMessage", 1
        )[1].split("\n}\n\nexport function setupCanvasDrag", 1)[0]

        self.assertIn("reaction-feedback", render_block)
        self.assertIn("Optional feedback", render_block)
        self.assertIn(
            "feedbackLink.href = buildFeedbackContactUrl()",
            render_block,
        )
        self.assertIn(
            "const FEEDBACK_SOURCE = 'reaction_feedback'",
            feedback,
        )
        self.assertIn(
            "return `/contact/?source=${FEEDBACK_SOURCE}`",
            feedback,
        )
        self.assertIn(
            "bindFeedbackOpenCapture(feedbackLink)",
            render_block,
        )
        self.assertIn(
            "captureFeedbackPromptViewed(feedbackLink)",
            render_block,
        )
        self.assertIn(
            "const viewedFeedbackPrompts = new WeakSet<HTMLAnchorElement>()",
            feedback,
        )
        self.assertIn("feedbackLink.onclick = captureFeedbackOpened", feedback)
        self.assertIn(
            "capture('reaction_feedback_prompt_viewed');",
            feedback,
        )
        self.assertIn(
            "capture('reaction_feedback_opened');",
            feedback,
        )
        self.assertIn("Stays in OmniLab. No lab details are added.", render_block)
        self.assertNotIn("mailto:", feedback)
        self.assertNotIn("FEEDBACK_EMAIL_ADDRESS", feedback)
        for private_value in (
            "selectedChemicals",
            "reaction.equation",
            "reaction.explanation",
            "reaction.safety",
        ):
            self.assertNotIn(private_value, feedback)
        self.assertNotIn("reaction-feedback", status_block)
        self.assertIn(".reaction-feedback-link", css)
        self.assertIn("min-height: 44px;", css)

    def test_feedback_link_uses_no_visit_or_guide_source(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        feedback = (
            settings.BASE_DIR / "static/ts/interactions/feedback.ts"
        ).read_text()

        self.assertIn("buildFeedbackContactUrl()", interactions)
        self.assertNotIn("getGuideVisitSource", feedback)
        self.assertNotIn("getVisitSource", feedback)
        self.assertNotIn("Guide source:", feedback)
        for non_guide_value in (
            "student_invite",
            "window.location",
            "URLSearchParams",
            "selectedChemicals",
            "reaction.equation",
            "reaction.explanation",
            "reaction.safety",
            "/guides/",
        ):
            with self.subTest(non_guide_value=non_guide_value):
                self.assertNotIn(non_guide_value, feedback)

    def test_reaction_results_render_only_mapped_guides_as_secondary_paths(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        configuration = (
            settings.BASE_DIR / "static/ts/configuration/config.ts"
        ).read_text()
        render_block = interactions.split(
            "export function renderReactionResult", 1
        )[1].split("\n}\n\nfunction renderStatusMessage", 1)[0]

        self.assertIn(
            "config.getMatchingReactionGuides(",
            render_block,
        )
        self.assertEqual(render_block.count('class="reaction-study"'), 1)
        for path, guide in (
            (
                "/guides/sodium-and-chlorine-reaction/",
                GUIDED_EXPERIMENT_PAGES["reaction"],
            ),
            (
                "/guides/sodium-and-chlorine-formula/",
                GUIDED_EXPERIMENT_PAGES["formula"],
            ),
            (
                "/guides/sodium-and-chlorine-ionic-bond/",
                GUIDED_EXPERIMENT_PAGES["ionic-bond"],
            ),
        ):
            with self.subTest(path=path):
                self.assertIn(f"href: '{path}'", configuration)
                self.assertIn(guide["title"], configuration)
        for guide in OBSERVATION_GUIDE_PAGES.values():
            path = PUBLIC_CANONICAL_URLS[guide["canonical_key"]].removeprefix(
                PRODUCTION_BASE_URL
            )
            with self.subTest(path=path):
                self.assertIn(f"href: '{path}'", configuration)
                self.assertIn(guide["title"], configuration)
        self.assertIn("matchingReactionGuides.map(guide =>", render_block)
        self.assertNotIn('class="btn', render_block)
        self.assertNotIn("action-btn-primary", render_block)
        self.assertNotIn("guide-primary", render_block)

    def test_live_and_restored_results_use_their_selected_pair_for_study_links(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        success_block = interactions.split(
            "} else if (resData.status === 'success' && resData.data) {", 1
        )[1].split("} else {", 1)[0]
        restore_block = interactions.split(
            "const savedData = readStorageValue(reactionStorageKey);", 1
        )[1]

        self.assertIn(
            "renderReactionResult(panel, reaction, state.selectedChemicals)",
            success_block,
        )
        self.assertIn(
            "renderReactionResult(panel, savedReaction, preparedChemicals)",
            restore_block,
        )

    def test_reset_removes_the_result_only_study_block(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        reset_block = interactions.split(
            "export function resetLaboratory(): void {", 1
        )[1].split("\n}\n\nfunction getCsrfToken", 1)[0]

        self.assertIn("panel.innerHTML = getDefaultReactionInstruction()", reset_block)
        self.assertNotIn("reaction-study", reset_block)

    def test_browser_normalizes_effects_before_measurement_storage_and_rendering(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        success_block = interactions.split(
            "} else if (resData.status === 'success' && resData.data) {", 1
        )[1].split("} else {", 1)[0]
        restore_block = interactions.split(
            "const savedData = readStorageValue(reactionStorageKey);", 1
        )[1]

        normalization_index = success_block.index(
            "const reaction = normalizeReactionResult(resData.data);"
        )
        capture_index = success_block.index(
            "capture('reaction_analysis_completed', {"
        )
        storage_index = success_block.index("JSON.stringify(reaction)")
        render_index = success_block.index(
            "renderReactionResult(panel, reaction, state.selectedChemicals);"
        )
        self.assertLess(normalization_index, capture_index)
        self.assertLess(normalization_index, storage_index)
        self.assertLess(normalization_index, render_index)
        self.assertIn("effect: reaction.effect", success_block)
        self.assertNotIn("precipitate_color: reaction.precipitate_color", success_block)
        self.assertNotIn("new_color", interactions)
        self.assertNotIn("triggerSmokeEffect", interactions)
        self.assertNotIn("return { ...reaction, effect }", interactions)
        self.assertIn("parseSavedReactionResult(savedData)", restore_block)
        self.assertIn(
            "writeStorageValue(reactionStorageKey, JSON.stringify(savedReaction))",
            restore_block,
        )

    def test_browser_rejects_incomplete_saved_reactions_before_rendering(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        restore_block = interactions.split(
            "const savedData = readStorageValue(reactionStorageKey);", 1
        )[1]

        validation_index = restore_block.index(
            "const savedReaction = parseSavedReactionResult(savedData);"
        )
        render_index = restore_block.index(
            "renderReactionResult(panel, savedReaction, preparedChemicals);"
        )
        self.assertLess(validation_index, render_index)
        self.assertIn("if (savedData !== null) {", restore_block)
        self.assertIn("removeStorageValue(reactionStorageKey);", restore_block)
        self.assertIn("? DEMO_REACTION_INSTRUCTION", restore_block)
        self.assertIn(": getDefaultReactionInstruction()", restore_block)
        self.assertNotIn("capture('reaction_analysis_completed'", restore_block)

    def test_browser_discards_invalid_saved_liquid_colors(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        restore_block = interactions.split(
            'document.addEventListener("DOMContentLoaded", () => {', 1
        )[1]

        self.assertIn(
            "return color !== null && /^#[0-9a-f]{6}$/i.test(color);",
            interactions,
        )
        self.assertIn(
            "removeStorageValue(liquidColorStorageKey);",
            restore_block,
        )
        self.assertIn(
            "const preparedLiquidColor = savedLiquidColor || reactionDemo?.liquidColor;",
            restore_block,
        )

    def test_browser_uses_one_retry_state_without_completion_measurement(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()

        self.assertIn(
            "OmniLab couldn't complete this prediction. Please try again.",
            interactions,
        )
        self.assertEqual(interactions.count("renderReactionRetry(panel);"), 2)
        self.assertEqual(
            interactions.count("capture('reaction_analysis_completed', {"),
            1,
        )
        self.assertIn("stage: 'response'", interactions)
        self.assertIn("stage: 'network_or_parse'", interactions)
        self.assertNotIn("err instanceof Error ? err.message", interactions)

    def test_browser_renders_insufficient_input_as_an_educational_state(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()

        self.assertIn("resData.status === 'insufficient_input'", interactions)
        self.assertIn("Try a different setup", interactions)
        self.assertIn(
            "removeStorageValue(config.getLabStorageKey('savedReaction'))",
            interactions,
        )
        self.assertIn("stage: 'insufficient_input'", interactions)

    def test_reset_clears_saved_and_visible_reaction_state(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        reset_block = interactions.split(
            "export function resetLaboratory(): void {", 1
        )[1].split("\n}\n\nexport function fireAIAnalysis", 1)[0]

        self.assertIn(
            "removeStorageValue(config.getLabStorageKey('savedChemicals'))",
            reset_block,
        )
        self.assertIn(
            "removeStorageValue(config.getLabStorageKey('savedLiquidColor'))",
            reset_block,
        )
        self.assertIn(
            "removeStorageValue(config.getLabStorageKey('savedReaction'))",
            reset_block,
        )
        self.assertIn("activeAnalysisController?.abort()", reset_block)
        self.assertIn("cancelReactionEffects()", reset_block)
        self.assertIn("selectedChemicals: []", reset_block)
        self.assertIn("isBubbling: false", reset_block)
        self.assertIn("smokeParticles: []", reset_block)
        self.assertIn("explosionParticles: []", reset_block)
        self.assertIn("precipitateColor: null", reset_block)
        self.assertIn("panel.innerHTML = getDefaultReactionInstruction()", reset_block)

    def test_reset_cancels_stale_analysis_and_thermal_effects(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        rendering = (
            settings.BASE_DIR / "static/ts/rendering/render.ts"
        ).read_text()

        self.assertIn("signal: requestController.signal", interactions)
        self.assertIn(
            "analysisRunId !== currentAnalysisRunId",
            interactions,
        )
        self.assertIn("export function cancelReactionEffects()", rendering)
        self.assertIn("clearInterval(thermalBlastTimer)", rendering)

    def test_browser_allows_only_one_in_flight_analysis(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        analysis_block = interactions.split(
            "export function fireAIAnalysis(): void {", 1
        )[1].split('\n}\n\ndocument.addEventListener("DOMContentLoaded"', 1)[0]

        guard_position = analysis_block.index(
            "if (activeAnalysisController) return;"
        )
        request_position = analysis_block.index("new AbortController()")
        fetch_position = analysis_block.index("fetch('/ai_insights/'")

        self.assertLess(guard_position, request_position)
        self.assertLess(request_position, fetch_position)
        self.assertNotIn("activeAnalysisController?.abort()", analysis_block)
        self.assertIn("setAnalysisPending(true)", analysis_block)

    def test_every_analysis_exit_restores_the_analyze_control(self):
        interactions = (
            settings.BASE_DIR / "static/ts/interactions/interactions.ts"
        ).read_text()
        pending_helper = interactions.split(
            "function setAnalysisPending", 1
        )[1].split("\n}\n\ninterface ReactionData", 1)[0]
        analysis_block = interactions.split(
            "export function fireAIAnalysis(): void {", 1
        )[1].split('\n}\n\ndocument.addEventListener("DOMContentLoaded"', 1)[0]
        reset_block = interactions.split(
            "export function resetLaboratory(): void {", 1
        )[1].split("\n}\n\nfunction getCsrfToken", 1)[0]

        self.assertIn("updateAnalysisAvailability()", pending_helper)
        self.assertIn("setAttribute('aria-busy'", pending_helper)
        self.assertIn(".finally(() => {", analysis_block)
        self.assertIn("activeAnalysisController = null", analysis_block)
        self.assertIn("setAnalysisPending(false)", analysis_block)
        self.assertIn("setAnalysisPending(false)", reset_block)
        self.assertNotIn("resetBtn.disabled", interactions)
