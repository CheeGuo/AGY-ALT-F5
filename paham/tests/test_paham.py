"""
Offline tests for Paham's deterministic layer (no API key or network needed).

Run:  py -m unittest discover -s paham/tests -t .
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Must be set before paham.config is imported: keep test sessions out of the real database
_TMP = tempfile.TemporaryDirectory()
os.environ["PAHAM_SESSION_DB"] = os.path.join(_TMP.name, "test.db")

from google.genai import types  # noqa: E402

from paham import channels, tools  # noqa: E402
from google.adk.models.llm_response import LlmResponse  # noqa: E402
from paham.agent import end_on_full_sentence, trim_history  # noqa: E402
from paham.prompts import build_instruction  # noqa: E402


class FakeToolContext:
    """Just enough of ADK's ToolContext for the tools: a mutable state mapping."""

    def __init__(self, state=None):
        self.state = dict(state or {})


class DataPackTests(unittest.TestCase):
    def test_every_glossary_term_has_every_language(self):
        glossary = tools.load_glossary()
        languages = [code for code in glossary["languages"] if code != "en"]
        for key, entry in glossary["terms"].items():
            for code in languages:
                self.assertTrue(entry.get(code), f"{key} missing {code}")

    def test_lessons_are_complete(self):
        glossary_terms = tools.load_glossary()["terms"]
        seen_ids = set()
        for lesson in tools.load_lessons().values():
            self.assertEqual(set(lesson["examples"]), set(tools.REGIONS), lesson["id"])
            for term in lesson["terms"]:
                self.assertIn(term, glossary_terms, f"{lesson['id']} references unknown term {term}")
            for item in lesson["practice"]:
                self.assertNotIn(item["id"], seen_ids)
                seen_ids.add(item["id"])
                for field in ("question", "hint", "solution"):
                    self.assertTrue(item.get(field), f"{item['id']} missing {field}")

    def test_every_practice_item_accepts_its_own_answer(self):
        for _, item in tools.practice_index().values():
            kind = item.get("type", "number")
            answer = str(item["answer"]) if kind == "number" else item["solution"]
            self.assertTrue(tools.grade_answer(item, answer), f"{item['id']} rejects its own answer {answer!r}")


class NumberParsingTests(unittest.TestCase):
    def test_formats(self):
        cases = [
            ("3/4", "", 0.75), ("1 1/2", "", 1.5), ("x = 5", "", 5), ("12 km/h", "", 12), ("-3", "", -3),
            ("0,75", "en", 0.75), ("0,75", "id", 0.75), ("1,500", "en", 1500), ("1,500", "id", 1.5),
            ("1.500", "id", 1500), ("1.500", "en", 1.5), ("0.375", "id", 0.375), ("2.345,5", "es", 2345.5),
            ("१२", "hi", 12), ("௧௨", "ta", 12), ("jawapan ialah 84 m²", "ms", 84),
            # Units with digits are not the answer
            ("0,6 g/cm3", "ms", 0.6), ("4 m/s2", "", 4), ("84 m^2", "", 84), ("x2 = 10", "", 10),
        ]
        for text, lang, expected in cases:
            value, _ = tools.parse_number(text, lang)
            self.assertAlmostEqual(value, expected, msg=f"{text!r} ({lang})")

    def test_percent_flag_and_unreadable(self):
        self.assertEqual(tools.parse_number("45%"), (45.0, True))
        self.assertIsNone(tools.parse_number("no idea"))


class GradingTests(unittest.TestCase):
    def item(self, qid):
        return tools.practice_index()[qid][1]

    def test_numeric_equivalents(self):
        half = self.item("fractions-1")
        for answer in ("1/2", "2/4", "0.5", "0,5", "jawapan: 1/2"):
            self.assertTrue(tools.grade_answer(half, answer), answer)
        self.assertFalse(tools.grade_answer(half, "2/6"))
        self.assertTrue(tools.grade_answer(self.item("probability-1"), "40%"))

    def test_multilingual_free_text(self):
        floats = self.item("density-2")
        for answer in ("It floats", "terapung", "Ia akan mengapung", "它会浮起来", "nổi", "itaelea", "flota", "மிதக்கும்", "तैरेगा"):
            self.assertTrue(tools.grade_answer(floats, answer), answer)
        for answer in ("it will sink", "tenggelam", "chìm", "डूब जाएगा"):
            self.assertFalse(tools.grade_answer(floats, answer), answer)
        oxygen = self.item("photosynthesis-1")
        self.assertTrue(tools.grade_answer(oxygen, "O₂"))
        self.assertFalse(tools.grade_answer(oxygen, "CO2"))
        self.assertFalse(tools.grade_answer(oxygen, "carbon dioxide"))

    def test_exact_answers(self):
        binary = self.item("binary_numbers-2")
        self.assertTrue(tools.grade_answer(binary, "It is 110"))
        self.assertFalse(tools.grade_answer(binary, "1100"))


class PracticeFlowTests(unittest.TestCase):
    def test_hint_then_solution_then_progress(self):
        ctx = FakeToolContext({"user:language": "ms"})
        question = tools.get_practice_question("percentages", ctx)
        self.assertEqual(question["question_id"], "percentages-1")
        self.assertNotIn("answer", question)

        self.assertEqual(tools.check_answer("percentages-1", "saya tak tahu", ctx)["status"], "unreadable")
        first = tools.check_answer("percentages-1", "20", ctx)
        self.assertFalse(first["correct"])
        self.assertIn("hint", first)
        self.assertNotIn("solution", first)
        second = tools.check_answer("percentages-1", "25", ctx)
        self.assertIn("solution", second)

        self.assertTrue(tools.check_answer("percentages-1", "30", ctx)["correct"])
        self.assertEqual(ctx.state["user:progress"]["percentages"]["solved"], ["percentages-1"])
        self.assertEqual(tools.get_practice_question("percentages", ctx)["question_id"], "percentages-2")

        report = tools.get_progress_report(ctx)
        self.assertEqual(report["topics"][0]["attempted"], 3)

    def test_unknown_question(self):
        self.assertEqual(tools.check_answer("nope-1", "5", FakeToolContext())["status"], "unknown_question")


class GlossaryAndTopicTests(unittest.TestCase):
    def test_reverse_and_fuzzy_lookup(self):
        ctx = FakeToolContext({"user:language": "ta"})
        self.assertEqual(tools.lookup_stem_term("ketumpatan", ctx)["english"], "density")
        self.assertEqual(tools.lookup_stem_term("光合作用", ctx)["english"], "photosynthesis")
        self.assertEqual(tools.lookup_stem_term("Cells", ctx)["english"], "cell")
        self.assertEqual(tools.lookup_stem_term("molecules", ctx)["english"], "molecule")
        self.assertEqual(tools.lookup_stem_term("density", ctx)["local_term"], "அடர்த்தி")
        self.assertEqual(tools.lookup_stem_term("density", ctx, language="Kiswahili")["local_term"], "msongamano")
        self.assertEqual(tools.lookup_stem_term("quantum chromodynamics", ctx)["status"], "not_found")

    def test_topic_resolution(self):
        for text, expected in [("Ohm's law", "electricity"), ("pecahan", "fractions"), ("float or sink", "density"),
                               ("binary", "binary_numbers"), ("for loop", "programming_basics")]:
            self.assertEqual(tools.resolve_topic(text), expected, text)
        self.assertIsNone(tools.resolve_topic("xyz"))

    def test_lesson_card_is_localized(self):
        ctx = FakeToolContext({"user:language": "sw", "user:region": "africa"})
        card = tools.get_lesson_card("density", ctx)
        self.assertIn("fishing boats", card["local_example"])
        self.assertEqual(card["key_terms"]["density"], "msongamano")


class ProfileTests(unittest.TestCase):
    def test_normalizes_language_and_region(self):
        ctx = FakeToolContext()
        tools.set_learner_profile(ctx, language="Bahasa Melayu", grade_level="Form 2", country="Kenya", data_saver="on")
        profile = tools.get_profile(ctx.state)
        self.assertEqual(profile["language"], "ms")
        self.assertEqual(profile["region"], "africa")
        self.assertTrue(profile["data_saver"])
        self.assertEqual(tools.normalize_language("es-MX"), "es")
        self.assertEqual(tools.normalize_language("Iban"), "iban")

    def test_instruction_reflects_profile_and_channel(self):
        text = build_instruction({"user:language": "ta", "channel": "sms"})
        self.assertIn("தமிழ்", text)
        self.assertIn("SMS channel", text)
        default = build_instruction({})
        self.assertIn("Bahasa Melayu Malaysia by default", default)
        self.assertIn("Two-Phase Teaching Protocol", default)


class CalculatorTests(unittest.TestCase):
    def test_results(self):
        for expr, expected in [("0.15 * 200", 30), ("sqrt(3**2 + 4**2)", 5), ("25% * 80", 20), ("sin(30)", 0.5),
                               ("12 ÷ 4 × 2", 6), ("2^3", 8), ("(20 - 0) / 5", 4)]:
            self.assertAlmostEqual(tools.calculate(expr)["result"], expected, msg=expr)

    def test_rejects_unsafe_or_huge(self):
        for expr in ("__import__('os').system('dir')", "2**10**10", "1/0", "open('x')", "x + 1", "a" * 300):
            self.assertEqual(tools.calculate(expr)["status"], "error", expr)


class ChannelTests(unittest.TestCase):
    def test_gsm_detection_and_segments(self):
        self.assertTrue(channels.is_gsm7("ketumpatan (density) = jisim / isi padu"))
        self.assertFalse(channels.is_gsm7("அடர்த்தி"))
        self.assertEqual(channels.sms_segments("a" * 160), 1)
        self.assertEqual(channels.sms_segments("a" * 161), 2)
        self.assertEqual(channels.sms_segments("அ" * 70), 1)
        self.assertEqual(channels.sms_segments("அ" * 71), 2)

    def test_sms_friendly_keeps_gsm(self):
        text = channels.sms_friendly("**Density** – it’s mass ÷ volume, in g/cm³")
        self.assertTrue(channels.is_gsm7(text), text)
        self.assertNotIn("**", text)

    def test_pagination_respects_budget(self):
        for sentence in ("Density is mass divided by volume. ", "அடர்த்தி என்பது நிறையை கனஅளவால் வகுப்பது. "):
            pages = channels.paginate_sms(sentence * 30, max_segments=3)
            self.assertGreater(len(pages), 1)
            for page in pages:
                self.assertLessEqual(channels.sms_segments(page), 3, page)
            for page in pages[:-1]:
                self.assertTrue(page.endswith("(MORE)"))

    def test_plain_text(self):
        self.assertEqual(channels.to_plain_text("## Step 1\n**Bold** and `code` and [link](http://x)"),
                         "Step 1\nBold and code and link")


def _content(role, text=None, image=False, function_response=False):
    parts = []
    if text:
        parts.append(types.Part.from_text(text=text))
    if image:
        parts.append(types.Part.from_bytes(data=b"\xff\xd8fake", mime_type="image/jpeg"))
    if function_response:
        parts.append(types.Part.from_function_response(name="calculate", response={"result": 1}))
    return types.Content(role=role, parts=parts)


class HistoryTrimTests(unittest.TestCase):
    def test_keeps_recent_turns_and_drops_old_media(self):
        contents = []
        for i in range(6):
            contents.append(_content("user", f"q{i}", image=True))
            contents.append(_content("model", f"a{i}"))
            contents.append(_content("user", function_response=True))
        trimmed = trim_history(contents, max_turns=4, media_turns=2)

        learner_turns = [c for c in trimmed if c.role == "user" and c.parts[0].text]
        self.assertEqual([c.parts[0].text for c in learner_turns], ["q2", "q3", "q4", "q5"])
        with_media = [c.parts[0].text for c in learner_turns if any(p.inline_data for p in c.parts)]
        self.assertEqual(with_media, ["q4", "q5"])
        self.assertTrue(all(any(p.inline_data for p in c.parts) for c in contents[::3]), "original events mutated")


class SentenceEndTests(unittest.TestCase):
    def response(self, text, reason):
        return LlmResponse(content=types.Content(role="model", parts=[types.Part.from_text(text=text)]),
                           finish_reason=reason)

    def test_trims_capped_reply_to_last_sentence(self):
        cases = [("Usanisinuru ni mchakato. Mimea hutumia jua. Je, ungependa tujaribu swali moja", "Usanisinuru ni mchakato. Mimea hutumia jua."),
                 ("光合作用是植物制造食物的过程。植物需要阳光。你想试", "光合作用是植物制造食物的过程。植物需要阳光。"),
                 ("घनत्व द्रव्यमान को आयतन से भाग देना है। लकड़ी पानी पर तैरती है। क्या आप", "घनत्व द्रव्यमान को आयतन से भाग देना है। लकड़ी पानी पर तैरती है।")]
        for text, expected in cases:
            out = end_on_full_sentence(None, self.response(text, types.FinishReason.MAX_TOKENS))
            self.assertEqual(out.content.parts[0].text, expected)

    def test_leaves_complete_replies_alone(self):
        self.assertIsNone(end_on_full_sentence(None, self.response("Done. Mostly", types.FinishReason.STOP)))


class LessonNotesTests(unittest.TestCase):
    def test_uploaded_notes_are_searched(self):
        from paham import notes
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(notes, "LESSONS_DIR", Path(tmp)):
            self.assertEqual(notes.search_lesson_notes("pecahan")["status"], "not_found")
            (Path(tmp) / "pecahan.md").write_text(
                "Pecahan setara: darab pengangka dan penyebut dengan nombor sama.\n\nKadar tindak balas naik bila suhu naik.",
                encoding="utf-8")
            hit = notes.search_lesson_notes("pecahan setara")
            self.assertEqual(hit["status"], "found")
            self.assertIn("Pecahan setara", hit["passages"][0]["text"])
            self.assertIn("pecahan.md", build_instruction({}))  # instruction tells the model notes exist


class LiteServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from paham.lite import server
        cls.server = server
        cls.client = TestClient(server.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_app_shell_is_small(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertLess(len(res.content), 40_000)

    def test_chat_validation(self):
        self.assertEqual(self.client.post("/api/chat", data={"learner_id": "bad id!"}).status_code, 400)
        self.assertEqual(self.client.post("/api/chat", data={"learner_id": "w-12345678"}).status_code, 400)
        res = self.client.post("/api/chat", data={"learner_id": "w-12345678"},
                               files={"image": ("x.gif", b"GIF89a", "image/gif")})
        self.assertEqual(res.status_code, 415)

    def test_chat_passes_media_and_state(self):
        fake = mock.AsyncMock(return_value="**Jawapan:** 1/2")
        with mock.patch.object(self.server, "ask_tutor", fake):
            res = self.client.post(
                "/api/chat",
                data={"learner_id": "w-12345678", "data_saver": "1", "language": "Bahasa Melayu"},
                files={"image": ("hw.jpg", b"\xff\xd8\xff\xe0jpeg", "image/jpeg")},
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["reply"], "**Jawapan:** 1/2")
        _, _, parts, state_delta = fake.call_args.args
        self.assertIn("a photo", parts[0].text)
        self.assertEqual(parts[1].inline_data.mime_type, "image/jpeg")
        self.assertEqual(state_delta["user:language"], "ms")
        self.assertTrue(state_delta["user:data_saver"])

    def test_sms_paging_without_model_calls(self):
        long_reply = "Ketumpatan ialah jisim dibahagi isi padu. " * 25
        fake = mock.AsyncMock(return_value=long_reply)
        with mock.patch.object(self.server, "ask_tutor", fake):
            first = self.client.post("/sms", data={"From": "+60123456789", "Body": "apa itu ketumpatan"})
            more = self.client.post("/sms", data={"From": "+60123456789", "Body": "LAGI"})
        self.assertEqual(fake.await_count, 1, "MORE should be served from the page buffer")
        self.assertIn("(MORE)", first.text)
        self.assertIn("<Message>", more.text)
        self.assertNotIn("+60123456789", str(fake.call_args), "raw phone number leaked into the agent")


if __name__ == "__main__":
    unittest.main()
