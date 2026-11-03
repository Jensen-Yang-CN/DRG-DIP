import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import DemoHandler


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_catalog_and_group_api(self):
        with urlopen(self.url + "/api/catalog") as response:
            catalog = json.load(response)
        self.assertEqual(catalog["coreCount"], 5125)
        self.assertTrue(any(item["code"] == "J18.9" for item in catalog["suggestions"]["dx"]))

        request = Request(
            self.url + "/api/group",
            data=json.dumps({"diagnoses": ["J18.900"], "operations": ["33.2402"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            result = json.load(response)
        self.assertEqual(result["hit"]["key"], "BX-774")
        self.assertEqual(result["sourceSheetName"], "二、并项规则下的核心病种")

    def test_drg_catalog_search_and_group(self):
        with urlopen(self.url + "/api/catalog?mode=drg") as response:
            catalog = json.load(response)
        self.assertEqual(catalog["referenceCount"], 825)
        with urlopen(self.url + "/api/search?mode=drg&kind=dx&q=J18.000") as response:
            suggestions = json.load(response)["suggestions"]
        self.assertEqual(suggestions[0]["name"], "支气管肺炎")
        request = Request(
            self.url + "/api/group",
            data=json.dumps({"mode": "drg", "diagnoses": ["J18.000", "N39.000", "N17.900"],
                             "operations": [], "sex": "男", "age": 30, "lengthOfStay": 15}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            result = json.load(response)
        self.assertEqual(result["hit"]["code"], "ES41")
        self.assertEqual(result["hit"]["fee"], "9521.40")

    def test_pages_and_logo(self):
        for path in ("/", "/index.html", "/flow.html", "/flow.js", "/assets/pku-logo.png", "/app.js?v=public"):
            with self.subTest(path=path), urlopen(self.url + path) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-cache")

    def test_only_public_pages_and_assets_are_served(self):
        for path in ("/server.py", "/grouping.py", "/drg_grouping.py", "/data/rules.json",
                     "/data/drg_rules.json", "/assets/", "/README.md"):
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as error:
                    urlopen(self.url + path)
                self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
