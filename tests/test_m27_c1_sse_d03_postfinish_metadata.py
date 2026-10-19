"""D03: strict post-finish usage-only SSE chunks. TEST DATA ONLY.

No live model calls, no authorities, no signed Product claims.
"""
import sys,json,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/"src"/"knowledge_engine"))
import m27_c1_formal_workers_ai_sse as s
from test_m27_c1_formal_workers_ai_sse import complete,line

def usage(*,model=s.MODEL, prompt=12,completion=27,total=39,extras=None,choices=None):
    data={"model":model,
          "choices":[] if choices is None else choices,
          "usage":{"prompt_tokens":prompt,"completion_tokens":completion,
                   "total_tokens":total}}
    if extras:data.update(extras)
    return b"data: "+json.dumps(data,separators=(",",":")).encode()+b"\n"

def decode(lines):
    audit=[]
    result=list(s.decode_sse(lines,model=s.MODEL,
        request_id="CURRENT_OWNER_C1_D03_TEST",audit=audit.append))
    return result,audit

class PostFinishUsageStrictness(unittest.TestCase):
    def test_01_optional_single_openai_usage_event_before_done(self):
        raw=complete()
        result,audit=decode(raw[:-1]+[usage()]+raw[-1:])
        self.assertEqual([entry["kind"] for _,entry in result],
                         ["delta","delta","done"])
        self.assertEqual(
            [item["meaning"] for item in audit],
            ["LIVE_NEW_PROVIDER_DELTA","LIVE_NEW_PROVIDER_DELTA",
             "REAL_PROVIDER_FINISH_STOP","NONANSWER_USAGE_METADATA_ONLY",
             "REAL_PROVIDER_DONE_FRAME"])
        self.assertNotIn("39","".join(item["text"] for _,item in result))
        self.assertEqual(sum(item["kind"]=="done" for _,item in result),1)

    def test_02_duplicate_usage_is_rejected(self):
        raw=complete()
        with self.assertRaisesRegex(s.WireRejected,"POSTFINISH"):
            decode(raw[:-1]+[usage(),usage()]+raw[-1:])

    def test_03_content_after_finish_is_rejected_even_as_usage_event(self):
        with self.assertRaisesRegex(s.WireRejected,"POSTFINISH"):
            decode(complete()[:-1]+[
             usage(choices=[{"delta":{"content":"UNSAFE LATE TEXT"},
                             "finish_reason":None}]),b"data: [DONE]\n"])

    def test_04_usage_empty_or_missing_or_negative_or_bool_counters_rejected(self):
        raws=[
          b'data: {"model":"@cf/openai/gpt-oss-120b","choices":[]}\n',
          b'data: {"model":"@cf/openai/gpt-oss-120b","choices":[],"usage":null}\n',
          usage(prompt=-1),usage(prompt=True),usage(total=1)]
        for frame in raws:
            with self.subTest(frame=frame):
                with self.assertRaisesRegex(s.WireRejected,"USAGE_INVALID"):
                    decode(complete()[:-1]+[frame,b"data: [DONE]\n"])

    def test_05_usage_wrong_model_and_unrecognized_fields_rejected(self):
        with self.assertRaisesRegex(s.WireRejected,"MODEL_MISMATCH"):
            decode(complete()[:-1]+[usage(model="fake-evil"),
                   b"data: [DONE]\n"])
        with self.assertRaisesRegex(s.WireRejected,"EXTRA_KEYS"):
            decode(complete()[:-1]+[usage(extras={"hidden_text":"late claim"}),
                   b"data: [DONE]\n"])

    def test_06_early_usage_before_stop_is_rejected(self):
        with self.assertRaisesRegex(s.WireRejected,"CHOICES_INVALID"):
            decode([usage()]+complete())

    def test_07_nothing_after_done_except_comment_and_whitespace(self):
        _,audit=decode(complete()[:-1]+[usage()]+complete()[-1:]+
            [b"\n",b": keepalive\n"])
        self.assertEqual(audit[-1]["meaning"],"REAL_PROVIDER_DONE_FRAME")
        with self.assertRaisesRegex(s.WireRejected,"AFTER_DONE"):
            decode(complete()[:-1]+[usage()]+complete()[-1:]+[usage()])

    def test_08_missing_real_done_with_usage_still_failclosed(self):
        with self.assertRaisesRegex(s.WireRejected,"INCOMPLETE"):
            decode(complete()[:-1]+[usage()])

if __name__=="__main__":unittest.main()
