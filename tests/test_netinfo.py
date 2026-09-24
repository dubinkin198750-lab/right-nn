"""Тесты backend/netinfo.py — в первую очередь регрессия на реальный
случай: вместо названия хостинг-компании в поле «Ответчик» попадал
технический идентификатор регистратора вида «lir-lv-podacini». А также
автоматическое определение email для жалоб (роль «abuse» в RDAP)."""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import netinfo  # noqa: E402


def _vcard(name=None, email=None, address_label=None, address_components=None):
    fields = [["version", {}, "text", "4.0"]]
    if name is not None:
        fields.append(["fn", {}, "text", name])
    if email is not None:
        fields.append(["email", {}, "text", email])
    if address_label is not None:
        fields.append(["adr", {"label": address_label}, "text", ["", "", "", "", "", "", ""]])
    elif address_components is not None:
        fields.append(["adr", {}, "text", address_components])
    return ["vcard", fields]


class TestExtractDomain(unittest.TestCase):
    def test_full_url(self):
        self.assertEqual(netinfo._extract_domain("https://example.com/page?x=1"), "example.com")

    def test_bare_domain(self):
        self.assertEqual(netinfo._extract_domain("example.com"), "example.com")

    def test_empty(self):
        self.assertEqual(netinfo._extract_domain(""), "")

    def test_lowercases(self):
        self.assertEqual(netinfo._extract_domain("https://EXAMPLE.COM"), "example.com")


class TestLooksLikeTechnicalHandle(unittest.TestCase):
    def test_lir_style_handle_is_technical(self):
        self.assertTrue(netinfo._looks_like_technical_handle("lir-lv-podacini"))

    def test_ripe_org_handle_is_technical(self):
        self.assertTrue(netinfo._looks_like_technical_handle("ORG-XY12-RIPE"))

    def test_real_company_name_with_space_is_not_technical(self):
        self.assertFalse(netinfo._looks_like_technical_handle("Cloudflare, Inc."))

    def test_real_company_name_no_hyphen_is_not_technical(self):
        self.assertFalse(netinfo._looks_like_technical_handle("Hetzner"))

    def test_hyphenated_company_name_still_flagged_as_handle(self):
        """Осознанное ограничение эвристики: реальные компании с дефисом в
        названии (редкость) тоже попадут под фильтр — это принятый
        компромисс, лучше пропустить редкое настоящее имя, чем показать
        десятки технических идентификаторов."""
        self.assertTrue(netinfo._looks_like_technical_handle("Hosting-Service"))


class TestRenderReadableRdapSummaryHtml(unittest.TestCase):
    """Собственная читаемая HTML-страница (запасной источник для
    скриншота-подтверждения) — регрессия на реальный найденный случай:
    раньше запасной вариант показывал сырой JSON с rdap.org на английском."""

    def test_includes_all_provided_values(self):
        html = netinfo.render_readable_rdap_summary_html(
            "188.137.180.27", "Podaon SIA", "abuse@podaon.com", domain="d3.dolinakursov.pro",
        )
        self.assertIn("188.137.180.27", html)
        self.assertIn("Podaon SIA", html)
        self.assertIn("abuse@podaon.com", html)
        self.assertIn("d3.dolinakursov.pro", html)

    def test_is_russian_not_raw_json(self):
        html = netinfo.render_readable_rdap_summary_html("1.2.3.4", "X", "y@x.test")
        self.assertIn("Сводка", html)
        self.assertNotIn('"entities"', html)  # не сырой JSON-ответ rdap.org

    def test_missing_values_show_placeholder_not_crash(self):
        html = netinfo.render_readable_rdap_summary_html("1.2.3.4", "", "")
        self.assertIn("не определено", html)

    def test_html_is_valid_utf8_and_escapes_special_characters(self):
        """Домен/название компании — потенциально пользовательский ввод,
        не должны ломать разметку страницы (XSS-подобная защита)."""
        html = netinfo.render_readable_rdap_summary_html(
            "1.2.3.4", '<script>alert(1)</script>', "y@x.test",
        )
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_renders_as_valid_screenshot_via_playwright(self):
        """Не только текстовая проверка — реально открываем страницу через
        Chromium (как это будет происходить в бою) и убеждаемся, что она
        рендерится без ошибок и получается непустой скриншот."""
        import base64
        from backend import screenshot_capture

        html = netinfo.render_readable_rdap_summary_html("1.2.3.4", "Test Org", "abuse@test.example")
        data_url = "data:text/html;charset=utf-8;base64," + base64.b64encode(html.encode("utf-8")).decode()
        result = screenshot_capture.capture(data_url)
        self.assertGreater(len(result["png_bytes"]), 0)


class TestFieldFromVcard(unittest.TestCase):
    def test_extracts_fn(self):
        self.assertEqual(netinfo._field_from_vcard(_vcard(name="Cloudflare, Inc."), "fn"), "Cloudflare, Inc.")

    def test_extracts_email(self):
        self.assertEqual(netinfo._field_from_vcard(_vcard(email="abuse@example.com"), "email"), "abuse@example.com")

    def test_missing_field_returns_none(self):
        self.assertIsNone(netinfo._field_from_vcard(_vcard(name="X"), "email"))

    def test_empty_vcard_returns_none(self):
        self.assertIsNone(netinfo._field_from_vcard(None, "fn"))
        self.assertIsNone(netinfo._field_from_vcard([], "fn"))


class TestRdapDetails(unittest.TestCase):
    def _mock_response(self, json_data):
        resp = MagicMock()
        resp.json.return_value = json_data
        resp.raise_for_status.return_value = None
        return resp

    def test_skips_technical_handle_prefers_real_name(self):
        """Регрессия на реальный найденный случай: первая entity в ответе —
        технический идентификатор LIR, вторая — настоящее название."""
        data = {
            "entities": [
                {"roles": ["registrant"], "vcardArray": _vcard(name="lir-lv-podacini")},
                {"roles": ["technical"], "vcardArray": _vcard(name="SIA Real Hosting Company")},
            ],
            "name": "NET-3-60",
        }
        with patch("requests.get", return_value=self._mock_response(data)):
            result = netinfo._rdap_details("188.137.180.27")
        self.assertEqual(result["hosting_org"], "SIA Real Hosting Company")

    def test_falls_back_to_network_name_when_all_entities_are_handles(self):
        data = {
            "entities": [
                {"roles": ["registrant"], "vcardArray": _vcard(name="lir-lv-podacini")},
            ],
            "name": "NET-3-60",
        }
        with patch("requests.get", return_value=self._mock_response(data)):
            result = netinfo._rdap_details("188.137.180.27")
        self.assertEqual(result["hosting_org"], "NET-3-60")

    def test_prefers_registrant_role_over_others_for_name(self):
        data = {
            "entities": [
                {"roles": ["technical"], "vcardArray": _vcard(name="Support Team LLC")},
                {"roles": ["registrant"], "vcardArray": _vcard(name="Real Owner Corp")},
            ],
        }
        with patch("requests.get", return_value=self._mock_response(data)):
            result = netinfo._rdap_details("1.2.3.4")
        self.assertEqual(result["hosting_org"], "Real Owner Corp")

    def test_checks_nested_entities_too(self):
        data = {
            "entities": [
                {"roles": ["registrant"], "vcardArray": None, "entities": [
                    {"vcardArray": _vcard(name="Nested Org Name")},
                ]},
            ],
        }
        with patch("requests.get", return_value=self._mock_response(data)):
            result = netinfo._rdap_details("1.2.3.4")
        self.assertEqual(result["hosting_org"], "Nested Org Name")

    def test_network_error_returns_none_values_not_exception(self):
        import requests
        with patch("requests.get", side_effect=requests.exceptions.Timeout()):
            result = netinfo._rdap_details("1.2.3.4")
        self.assertEqual(result, {"hosting_org": None, "hosting_address": None, "abuse_email": None})

    def test_no_entities_and_no_name_returns_none(self):
        with patch("requests.get", return_value=self._mock_response({})):
            result = netinfo._rdap_details("1.2.3.4")
        self.assertIsNone(result["hosting_org"])

    # --- email для жалоб (роль abuse) ---
    def test_extracts_abuse_email(self):
        data = {
            "entities": [
                {"roles": ["registrant"], "vcardArray": _vcard(name="Real Owner Corp")},
                {"roles": ["abuse"], "vcardArray": _vcard(name="Abuse Team", email="abuse@realowner.example")},
            ],
        }
        with patch("requests.get", return_value=self._mock_response(data)):
            result = netinfo._rdap_details("1.2.3.4")
        self.assertEqual(result["abuse_email"], "abuse@realowner.example")

    def test_no_abuse_role_means_no_email(self):
        data = {
            "entities": [
                {"roles": ["registrant"], "vcardArray": _vcard(name="Real Owner Corp", email="registrant@example.com")},
            ],
        }
        with patch("requests.get", return_value=self._mock_response(data)):
            result = netinfo._rdap_details("1.2.3.4")
        self.assertIsNone(result["abuse_email"])  # email есть, но не у роли abuse — не берём

    def test_abuse_email_found_in_nested_entity(self):
        data = {
            "entities": [
                {"roles": ["abuse"], "vcardArray": None, "entities": [
                    {"vcardArray": _vcard(email="nested-abuse@example.com")},
                ]},
            ],
        }
        with patch("requests.get", return_value=self._mock_response(data)):
            result = netinfo._rdap_details("1.2.3.4")
        self.assertEqual(result["abuse_email"], "nested-abuse@example.com")

    def test_abuse_role_without_email_field_leaves_none(self):
        data = {
            "entities": [
                {"roles": ["abuse"], "vcardArray": _vcard(name="Abuse Team")},  # без email
            ],
        }
        with patch("requests.get", return_value=self._mock_response(data)):
            result = netinfo._rdap_details("1.2.3.4")
        self.assertIsNone(result["abuse_email"])


class TestAddressFromVcard(unittest.TestCase):
    """Пункт 1 из запроса пользователя: адрес ответчика из официального
    источника (RDAP), не только вручную. Проверено на реальном RDAP-ответе
    ARIN по автономной системе Cloudflare (AS13335) — найден через поиск,
    формат подтверждён независимым источником, не выдуман."""

    def test_real_cloudflare_arin_response_short_label_format(self):
        """Точная копия реального ответа ARIN — короткая форма адреса
        через параметр "label", без заполненных отдельных компонентов."""
        vcard = _vcard(name="Cloudflare, Inc.", address_label="101 Townsend Street\n\nSan Francisco\nCA\n94107")
        self.assertEqual(
            netinfo._address_from_vcard(vcard),
            "101 Townsend Street, San Francisco, CA, 94107",
        )

    def test_standard_rfc_component_array_format(self):
        """Полная форма по RFC 6350/7095 — семь отдельных компонентов, без
        параметра "label" (так может отдавать RIPE/APNIC и другие)."""
        vcard = _vcard(name="Example Registrant", address_components=["", "Suite 1234", "4321 Rue Somewhere", "Quebec", "QC", "G1V 2M2", "Canada"])
        self.assertEqual(
            netinfo._address_from_vcard(vcard),
            "Suite 1234, 4321 Rue Somewhere, Quebec, QC, G1V 2M2, Canada",
        )

    def test_empty_components_are_skipped_not_shown_as_blank(self):
        """Пустые компоненты (например, «почтовый ящик» не указан) не
        должны превращаться в лишние пустые запятые в итоговой строке."""
        vcard = _vcard(name="X", address_components=["", "", "Only Street", "City", "", "", "Country"])
        self.assertEqual(netinfo._address_from_vcard(vcard), "Only Street, City, Country")

    def test_no_address_field_returns_none(self):
        """Многие провайдеры (особенно с приватностью WHOIS) вообще не
        публикуют адрес — не должно падать, просто None, поле остаётся
        для ручного заполнения."""
        vcard = _vcard(name="Приватный хостинг")
        self.assertIsNone(netinfo._address_from_vcard(vcard))

    def test_no_vcard_at_all_returns_none(self):
        self.assertIsNone(netinfo._address_from_vcard(None))

    def test_parse_rdap_details_includes_address_for_full_cloudflare_response(self):
        """Сквозная проверка на полном ответе — не только вырезанной
        функции разбора адреса саму по себе, а всей цепочки целиком,
        включая приоритет ролей (сначала registrant)."""
        data = {
            "entities": [
                {
                    "roles": ["registrant"],
                    "vcardArray": _vcard(name="Cloudflare, Inc.", address_label="101 Townsend Street\nSan Francisco\nCA\n94107"),
                },
                {
                    "roles": ["abuse"],
                    "vcardArray": _vcard(name="Abuse", email="abuse@cloudflare.com"),
                },
            ],
        }
        result = netinfo._parse_rdap_details(data)
        self.assertEqual(result["hosting_org"], "Cloudflare, Inc.")
        self.assertEqual(result["hosting_address"], "101 Townsend Street, San Francisco, CA, 94107")
        self.assertEqual(result["abuse_email"], "abuse@cloudflare.com")

    def test_prefers_registrant_address_over_other_roles(self):
        """Тот же приоритет ролей, что и для названия — сначала registrant,
        не первая попавшаяся запись с адресом."""
        data = {
            "entities": [
                {"roles": ["technical"], "vcardArray": _vcard(name="Tech", address_components=["", "", "Wrong St", "", "", "", ""])},
                {"roles": ["registrant"], "vcardArray": _vcard(name="Real Co", address_components=["", "", "Right St", "", "", "", ""])},
            ],
        }
        result = netinfo._parse_rdap_details(data)
        self.assertEqual(result["hosting_address"], "Right St")

    def test_no_address_anywhere_leaves_none_not_crash(self):
        data = {"entities": [{"roles": ["registrant"], "vcardArray": _vcard(name="Приватный")}]}
        result = netinfo._parse_rdap_details(data)
        self.assertIsNone(result["hosting_address"])


class TestOfficialRegistryUrl(unittest.TestCase):
    """Тесты определения официальной страницы регистратора (не через
    rdap.org-агрегатор, а напрямую у RIR) по полю port43."""

    def _mock_response(self, json_data):
        resp = MagicMock()
        resp.json.return_value = json_data
        resp.raise_for_status.return_value = None
        return resp

    def test_ripe_port43_maps_to_ripe_web_ui(self):
        with patch("requests.get", return_value=self._mock_response({"port43": "whois.ripe.net"})):
            rir, url = netinfo.official_registry_url("188.137.180.27")
        self.assertEqual(rir, "RIPE NCC")
        self.assertIn("188.137.180.27", url)
        self.assertTrue(url.startswith("https://apps.db.ripe.net/"))

    def test_arin_port43_maps_to_arin_web_ui(self):
        with patch("requests.get", return_value=self._mock_response({"port43": "whois.arin.net"})):
            rir, url = netinfo.official_registry_url("8.8.8.8")
        self.assertEqual(rir, "ARIN")
        self.assertTrue(url.startswith("https://search.arin.net/"))

    def test_unknown_registry_returns_none_none(self):
        with patch("requests.get", return_value=self._mock_response({"port43": "whois.something-unknown.net"})):
            rir, url = netinfo.official_registry_url("1.2.3.4")
        self.assertIsNone(rir)
        self.assertIsNone(url)

    def test_missing_port43_returns_none_none(self):
        with patch("requests.get", return_value=self._mock_response({})):
            rir, url = netinfo.official_registry_url("1.2.3.4")
        self.assertIsNone(rir)
        self.assertIsNone(url)

    def test_case_insensitive_port43_matching(self):
        with patch("requests.get", return_value=self._mock_response({"port43": "WHOIS.RIPE.NET"})):
            rir, url = netinfo.official_registry_url("1.2.3.4")
        self.assertEqual(rir, "RIPE NCC")

    def test_network_error_returns_none_none(self):
        import requests
        with patch("requests.get", side_effect=requests.exceptions.Timeout()):
            rir, url = netinfo.official_registry_url("1.2.3.4")
        self.assertIsNone(rir)
        self.assertIsNone(url)


class TestLookup(unittest.TestCase):

    def test_dns_failure_returns_empty_strings_not_exception(self):
        import socket
        with patch("socket.gethostbyname", side_effect=socket.gaierror("dns fail")):
            result = netinfo.lookup("does-not-resolve.test")
        self.assertEqual(result, {"ip_address": "", "hosting_org": "", "defendant_email": "", "defendant_address": ""})

    def test_successful_lookup_combines_all_fields(self):
        with patch.object(netinfo, "resolve_ip", return_value="188.137.180.27"), \
             patch.object(netinfo, "_rdap_details", return_value={
                 "hosting_org": "Real Hosting Company", "abuse_email": "abuse@example.com",
                 "hosting_address": "101 Test St, Testville, US",
             }):
            result = netinfo.lookup("example.test")
        self.assertEqual(result, {
            "ip_address": "188.137.180.27",
            "hosting_org": "Real Hosting Company",
            "defendant_email": "abuse@example.com",
            "defendant_address": "101 Test St, Testville, US",
        })

    def test_missing_email_becomes_empty_string_not_none(self):
        with patch.object(netinfo, "resolve_ip", return_value="1.2.3.4"), \
             patch.object(netinfo, "_rdap_details", return_value={"hosting_org": "X", "abuse_email": None}):
            result = netinfo.lookup("example.test")
        self.assertEqual(result["defendant_email"], "")


class TestCheckDefendantMatchesIp(unittest.TestCase):
    """Сверка вручную вписанного «Ответчика» с тем, что по IP реально
    показывает RDAP — ловит случай, когда IP в деле сменился (сайт
    переехал на другой хостинг), а поле «Ответчик» осталось от старого."""

    def test_matches_when_name_present_in_rdap_org(self):
        with patch.object(netinfo, "_rdap_details", return_value={"hosting_org": "Cloudflare, Inc."}):
            result = netinfo.check_defendant_matches_ip("1.2.3.4", "CloudFlare Inc. (КлаудФлэр Инк.)")
        self.assertTrue(result["checked"])
        self.assertTrue(result["matches"])

    def test_matches_against_network_name_fallback(self):
        """RDAP иногда возвращает не «человеческое» название организации,
        а имя сети верхнего уровня (например, «CLOUDFLARENET») — сравнение
        нестрогое, по вхождению значимого слова, это тоже должно засчитаться."""
        with patch.object(netinfo, "_rdap_details", return_value={"hosting_org": "CLOUDFLARENET"}):
            result = netinfo.check_defendant_matches_ip("1.2.3.4", "CloudFlare Inc.")
        self.assertTrue(result["matches"])

    def test_does_not_match_different_organization(self):
        """Реальный случай, который должен ловить эта проверка: IP сменился
        на другой хостинг, а поле «Ответчик» осталось от старого."""
        with patch.object(netinfo, "_rdap_details", return_value={"hosting_org": "DDOS-GUARD LTD"}):
            result = netinfo.check_defendant_matches_ip("5.6.7.8", "CloudFlare Inc. (КлаудФлэр Инк.)")
        self.assertTrue(result["checked"])
        self.assertFalse(result["matches"])

    def test_not_checked_when_ip_or_defendant_missing(self):
        self.assertFalse(netinfo.check_defendant_matches_ip("", "CloudFlare Inc.")["checked"])
        self.assertFalse(netinfo.check_defendant_matches_ip("1.2.3.4", "")["checked"])

    def test_not_checked_when_rdap_unavailable(self):
        with patch.object(netinfo, "_rdap_details", return_value={"hosting_org": None}):
            result = netinfo.check_defendant_matches_ip("1.2.3.4", "CloudFlare Inc.")
        self.assertFalse(result["checked"])
        self.assertTrue(result["matches"])  # не блокируем предупреждением, когда сверить не удалось

    def test_not_checked_when_defendant_has_no_latin_words(self):
        """Ответчик указан только кириллицей без латинского аналога для
        сравнения с RDAP (который обычно на латинице) — сверить нечем,
        должно тихо промолчать, а не ложно тревожить."""
        with patch.object(netinfo, "_rdap_details", return_value={"hosting_org": "Cloudflare, Inc."}):
            result = netinfo.check_defendant_matches_ip("1.2.3.4", "ООО «Рога и копыта»")
        self.assertFalse(result["checked"])

    def test_organization_suffixes_ignored(self):
        """«DDOS-GUARD LTD» и просто «DDOS-GUARD» в RDAP — должны совпасть,
        организационно-правовая форма не должна мешать сравнению."""
        with patch.object(netinfo, "_rdap_details", return_value={"hosting_org": "DDOS-GUARD LTD"}):
            result = netinfo.check_defendant_matches_ip("1.2.3.4", "DDOS-GUARD LTD (ООО «ДДОС-ГВАРД»)")
        self.assertTrue(result["matches"])


if __name__ == "__main__":
    unittest.main()
