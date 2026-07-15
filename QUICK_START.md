# JobApplier Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
python3 dashboard/app.py
```

Open <http://127.0.0.1:5000>. Add a public job description manually, preview its score, and save it. Use **Resume tailor** to create truthful drafts, review them, submit the application yourself on the official employer portal, then explicitly mark the tracker row applied.

Protected-board scraping, login automation, form filling, CAPTCHA handling, and final submission are not part of the supported product.

See [README.md](README.md) and [USAGE_GUIDE.md](USAGE_GUIDE.md).
