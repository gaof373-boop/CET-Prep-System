"""GitHub vocabulary source.

Tries three strategies, in order:
1. **GitHub Code Search API** — finds JSON / TXT files named like
   ``cet4`` or ``CET6`` in public repos.
2. **Curated list of known candidate URLs** — raw.githubusercontent.com
   paths that historically hosted CET-4/6 lists.
3. **Local fallback** — a curated chunk of high-frequency CET-4/6 words
   used only if every network attempt fails.

All fetched items are tagged with their source so the UI can label
provenance correctly.
"""

from __future__ import annotations

import json
import random
import re
from typing import Iterator

from crawler.base import BaseScraper, RawItem, log


GITHUB_SEARCH_API = "https://api.github.com/search/code"


# (level, list of (raw_url, parser_hint)) — best-effort known paths
CANDIDATES: list[tuple[str, list[tuple[str, str]]]] = [
    ("CET4", [
        ("https://raw.githubusercontent.com/kajweb/dict/master/CET4_T.json", "json"),
        ("https://raw.githubusercontent.com/kajweb/dict/master/cet4.json", "json"),
        ("https://raw.githubusercontent.com/mahavivo/english-wordlists/master/CET4_T.json", "json"),
        ("https://raw.githubusercontent.com/mahavivo/english-wordlists/master/cet4.json", "json"),
        ("https://raw.githubusercontent.com/yezihaohao/cet46/master/CET4_T.json", "json"),
        ("https://raw.githubusercontent.com/yezihaohao/cet46/master/cet4.json", "json"),
        ("https://raw.githubusercontent.com/icopy-site/awesome-cn-web/main/words/cet4.txt", "text"),
        ("https://raw.githubusercontent.com/MSWorker/cet46/master/data/cet4.json", "json"),
        ("https://raw.githubusercontent.com/airyland/vocabulary/master/CET4_T.json", "json"),
        ("https://raw.githubusercontent.com/cynthia0615/CET4-6/master/CET4.json", "json"),
        ("https://raw.githubusercontent.com/cynthia0615/CET4-6/master/cet4.json", "json"),
    ]),
    ("CET6", [
        ("https://raw.githubusercontent.com/kajweb/dict/master/CET6_T.json", "json"),
        ("https://raw.githubusercontent.com/kajweb/dict/master/cet6.json", "json"),
        ("https://raw.githubusercontent.com/mahavivo/english-wordlists/master/CET6_T.json", "json"),
        ("https://raw.githubusercontent.com/mahavivo/english-wordlists/master/cet6.json", "json"),
        ("https://raw.githubusercontent.com/yezihaohao/cet46/master/CET6_T.json", "json"),
        ("https://raw.githubusercontent.com/yezihaohao/cet46/master/cet6.json", "json"),
        ("https://raw.githubusercontent.com/airyland/vocabulary/master/CET6_T.json", "json"),
        ("https://raw.githubusercontent.com/cynthia0615/CET4-6/master/CET6.json", "json"),
        ("https://raw.githubusercontent.com/cynthia0615/CET4-6/master/cet6.json", "json"),
    ]),
]


# Fallback list of high-frequency CET words. Single English words and
# short glosses — not copyrightable creative content.
FALLBACK_WORDS: dict[str, list[str]] = {
    "CET4": [
        # (a few hundred extra high-frequency words, grouped roughly by
        # topic. Frequencies are not literal; we assign pseudo-stars.)
        "abandon", "ability", "able", "abnormal", "abolish", "absorb", "abstract",
        "abundant", "abuse", "academic", "accelerate", "accent", "accept", "access",
        "accident", "accommodation", "accompany", "accomplish", "according", "account",
        "accumulate", "accuracy", "accuse", "achieve", "acid", "acknowledge",
        "acquire", "acre", "action", "active", "activity", "actual", "adapt",
        "address", "adequate", "adjust", "administration", "admire", "admission",
        "admit", "adolescent", "adopt", "adore", "advance", "advantage", "adventure",
        "adverse", "advertise", "advice", "advise", "affair", "affect", "afford",
        "afraid", "agency", "agenda", "agent", "aggressive", "agree", "ahead",
        "aid", "aim", "aircraft", "airline", "airport", "alarm", "album", "alcohol",
        "alert", "alien", "alike", "alive", "alliance", "allow", "ally", "almost",
        "alone", "along", "already", "alter", "alternative", "although", "altitude",
        "altogether", "aluminum", "always", "amazing", "ambassador", "ambition",
        "ambitious", "ambulance", "amount", "amuse", "analyse", "analysis", "ancestor",
        "anchor", "ancient", "angle", "ankle", "anniversary", "announce", "annoy",
        "annual", "another", "anticipate", "anxiety", "anxious", "anyway", "apart",
        "apartment", "apologize", "apparent", "appeal", "appear", "appetite",
        "applaud", "applicable", "applicant", "application", "apply", "appoint",
        "appreciate", "approach", "appropriate", "approval", "approve", "approximate",
        "architect", "argue", "argument", "arise", "arrange", "arrest", "arrival",
        "arrive", "arrow", "article", "artificial", "artist", "ashamed", "aside",
        "aspect", "aspirin", "assemble", "assess", "asset", "assign", "assist",
        "associate", "assume", "assure", "athlete", "atmosphere", "atom", "attach",
        "attack", "attain", "attempt", "attend", "attitude", "attorney", "attract",
        "attractive", "auction", "audience", "author", "authority", "automatic",
        "available", "avenue", "average", "avoid", "awake", "award", "aware",
        "awful", "awkward", "bachelor", "back", "background", "backward", "bacon",
        "bacteria", "badge", "badly", "baffle", "balance", "balcony", "balloon",
        "banana", "band", "bang", "bankrupt", "banner", "banquet", "bargain",
        "barrier", "base", "basement", "basically", "basis", "basket", "bath",
        "battery", "beach", "beam", "bean", "bear", "beard", "beast", "beat",
        "because", "become", "before", "began", "begin", "behalf", "behave",
        "behavior", "behind", "being", "belief", "believe", "bell", "belong",
        "below", "belt", "bench", "bend", "beneath", "benefit", "beside", "betray",
        "beyond", "bicycle", "bid", "billion", "bin", "biology", "birth", "biscuit",
        "bishop", "bizarre", "blame", "blank", "blast", "bleed", "blend", "bless",
        "blind", "block", "blood", "bloom", "blossom", "blow", "blue", "board",
        "boast", "boat", "body", "boil", "bold", "bomb", "bond", "bone", "bonus",
        "book", "boom", "boost", "border", "bored", "born", "borrow", "boss",
        "bother", "bottle", "bottom", "bounce", "bound", "boundary", "bow", "bowl",
        "box", "boycott", "brain", "brake", "branch", "brand", "brass", "brave",
        "bread", "break", "breakdown", "breakfast", "breast", "breath", "breathe",
        "breed", "breeze", "brick", "bride", "bridge", "brief", "bright", "brilliant",
        "bring", "broad", "broadcast", "broom", "brother", "brown", "brush", "bubble",
        "bucket", "budget", "buffet", "bug", "build", "building", "bulb", "bull",
        "bullet", "bulletin", "bunch", "bundle", "burden", "bureau", "burial",
        "burn", "burst", "bury", "business", "busy", "butter", "button", "cabbage",
        "cabin", "cabinet", "cable", "cafe", "cafeteria", "cage", "cake", "calculate",
        "calendar", "calf", "call", "calm", "camel", "camera", "camp", "campaign",
        "campus", "canal", "cancel", "cancer", "candidate", "candle", "candy",
        "cannon", "canoe", "canvas", "canyon", "capable", "capacity", "capital",
        "captain", "capture", "carbon", "card", "career", "careful", "cargo",
        "carpet", "carriage", "carrier", "carrot", "carry", "cartoon", "case",
        "cash", "cassette", "cast", "castle", "casual", "catalog", "catch", "category",
        "cater", "cathedral", "cattle", "caught", "cause", "caution", "cave", "cease",
        "ceiling", "celebrate", "celebrity", "cell", "cellar", "cement", "cemetery",
        "center", "centigrade", "centimeter", "central", "century", "ceremony",
        "certain", "certificate", "chain", "chair", "chalk", "challenge", "chamber",
        "champion", "chance", "channel", "chapter", "character", "charge", "charity",
        "charming", "chart", "chase", "chat", "cheap", "cheat", "check", "cheek",
        "cheer", "cheese", "chef", "chemical", "chemistry", "cheque", "cherry",
        "chest", "chicken", "chief", "child", "chill", "chimney", "chin", "chip",
        "chocolate", "choice", "choke", "choose", "chop", "chord", "chorus", "chosen",
        "Christ", "Christian", "cigar", "cinema", "circle", "circuit", "circular",
        "circulate", "circumstance", "circus", "cite", "citizen", "civil", "civilian",
        "civilization", "claim", "clarify", "clarity", "clash", "class", "classic",
        "classify", "classmate", "classroom", "clause", "claw", "clay", "clean",
        "clear", "clerk", "clever", "click", "client", "cliff", "climate", "climb",
        "clinic", "clock", "close", "closet", "cloth", "clothes", "cloud", "clue",
        "clumsy", "coach", "coal", "coast", "coat", "code", "coffee", "coin",
        "coincidence", "coke", "cold", "collapse", "collar", "colleague", "collect",
        "college", "collide", "collision", "colonial", "colony", "color", "column",
        "combat", "combine", "comedy", "comet", "comfort", "coming", "command",
        "commander", "comment", "commerce", "commission", "commit", "committee",
        "common", "communicate", "community", "commute", "companion", "company",
        "compare", "compass", "compete", "compile", "complain", "complement",
        "complete", "complex", "complicate", "comply", "component", "compose",
        "composition", "compound", "comprehend", "compress", "comprise", "compromise",
        "compulsory", "computer", "comrade", "conceal", "concentrate", "concept",
        "concern", "conclude", "concrete", "condemn", "condition", "conduct",
        "confer", "conference", "confess", "confidence", "confine", "confirm",
        "conflict", "confront", "confuse", "congratulate", "congress", "conjunction",
        "connect", "conquer", "conscience", "conscious", "consensus", "consent",
        "consequence", "conservative", "conserve", "consider", "consist", "constant",
        "constitute", "constitution", "constrain", "construct", "consult", "consume",
        "contact", "contain", "contemporary", "content", "contest", "context",
        "continent", "continual", "continue", "contract", "contradict", "contrary",
        "contrast", "contribute", "control", "convention", "conversation", "convert",
        "convey", "convict", "convince", "cook", "cool", "cooperate", "coordinate",
        "cope", "copper", "copy", "cord", "core", "corn", "corner", "corporate",
        "corps", "correct", "correspond", "corrupt", "cosmic", "cost", "costume",
        "cottage", "cotton", "couch", "cough", "could", "council", "count", "counter",
        "country", "county", "couple", "coupon", "courage", "course", "court",
        "courtesy", "courtyard", "cousin", "cover", "cow", "coward", "cowboy",
        "cozy", "crab", "crack", "craft", "crane", "crash", "crawl", "crazy",
        "cream", "create", "creation", "creative", "creature", "credit", "crew",
        "cricket", "crime", "criminal", "crisis", "crisp", "critic", "critical",
        "criticize", "crop", "cross", "crouch", "crowd", "crown", "crucial", "crude",
        "cruel", "cruise", "crush", "cry", "crystal", "cube", "cucumber", "cue",
        "cuisine", "cultivate", "cultural", "culture", "cunning", "cup", "cupboard",
        "curb", "cure", "curiosity", "curious", "curl", "currency", "current",
        "curriculum", "curry", "curtain", "curve", "cushion", "custom", "customer",
        "customs", "cut", "cute", "cycle", "cylinder",
    ],
    "CET6": [
        "aberration", "abhor", "abide", "abjure", "ablaze", "abolish", "abominable",
        "aboriginal", "abort", "abound", "abrasive", "abridge", "absent", "absolute",
        "absorb", "abstain", "abstract", "absurd", "abundant", "abuse", "accelerate",
        "accessible", "accidental", "acclaim", "acclimate", "accommodate", "accompany",
        "accomplice", "accord", "accountable", "accredit", "accumulate", "accuracy",
        "accusation", "accustom", "acerbic", "acknowledge", "acquaint", "acquire",
        "acquit", "acronym", "activate", "adaptation", "addict", "address", "adept",
        "adhere", "adjacent", "adjoin", "adjudicate", "adjunct", "admire", "admission",
        "admonish", "adore", "adorn", "adulation", "adversary", "adverse", "advocate",
        "aesthetic", "affable", "affectation", "affiliate", "affirm", "afflict",
        "affluent", "afford", "aggravate", "aggregate", "agile", "agitate", "agonize",
        "agreeable", "ailment", "airborne", "albeit", "alchemy", "alcove", "alienate",
        "align", "allay", "allege", "allegiance", "alleviate", "allocate", "allowance",
        "allure", "ally", "aloof", "altercation", "alumni", "amalgamate", "amass",
        "amateur", "ambiguous", "ambition", "ambivalent", "ameliorate", "amenable",
        "amend", "amenity", "amiable", "amicable", "amnesia", "amnesty", "among",
        "amorphous", "ample", "amplify", "amuse", "analgesic", "analogous", "analyst",
        "analyze", "anarchy", "anatomy", "ancestor", "anchor", "anecdote", "anguish",
        "animate", "animosity", "ankle", "annex", "annihilate", "annotate", "announce",
        "annoy", "annual", "annul", "anomaly", "anonymous", "antagonist", "antarctic",
        "antecedent", "antenna", "anthem", "anthropology", "antibiotic", "anticipate",
        "antipathy", "antiquated", "antiquity", "antithesis", "anxiety", "apartheid",
        "apathy", "apex", "apocalypse", "apocryphal", "apology", "apostle", "appall",
        "apparent", "apparition", "appeal", "appease", "appendix", "applaud", "appliance",
        "applicant", "apprehend", "apprentice", "approach", "appropriation", "approval",
        "approximate", "apricot", "aptitude", "aquatic", "arabesque", "arbitrary",
        "arbitrate", "arboreal", "arcade", "archaic", "archetype", "archive", "arctic",
        "ardent", "arduous", "arena", "argument", "aristocrat", "armada", "armistice",
        "aroma", "arouse", "arrange", "array", "arrest", "arrogant", "arsenal",
        "arson", "artery", "articulate", "artifact", "artifice", "artisan", "asbestos",
        "ascend", "ascertain", "ascribe", "ashore", "aspirant", "aspire", "assail",
        "assassin", "assault", "assay", "assemble", "assent", "assert", "assess",
        "asset", "assiduous", "assign", "assimilate", "assist", "assorted", "assuage",
        "assume", "assure", "asterisk", "astound", "astute", "asylum", "atone",
        "atrocious", "atrophy", "attach", "attain", "attempt", "attend", "attentive",
        "attest", "attic", "attire", "attorney", "attract", "attribute", "auction",
        "audit", "augment", "august", "auspicious", "austere", "authentic", "author",
        "autocrat", "automatic", "autonomous", "autopsy", "auxiliary", "avail",
        "avalanche", "avant-garde", "avenge", "avenue", "averse", "aversion", "avert",
        "aviary", "avid", "avocation", "avoid", "avow", "await", "awake", "aware",
        "awesome", "awful", "awkward", "axiom", "babble", "backbone", "baffle",
        "bald", "ballad", "bamboo", "banal", "bandit", "banish", "banquet", "banshee",
        "barbaric", "barley", "barometer", "barrage", "barren", "barricade", "barrier",
        "barter", "basil", "batter", "beacon", "beadle", "begrudge", "behave",
        "beleaguered", "belie", "belittle", "belligerent", "bemoan", "benchmark",
        "benevolent", "benign", "bequeath", "berate", "bereft", "beseech", "besiege",
        "bestow", "betray", "beverage", "bewilder", "bias", "bickering", "biennial",
        "bifurcate", "bigot", "bilateral", "bilingual", "billion", "binary", "binoculars",
        "biography", "biology", "bipartisan", "bizarre", "blanch", "bland", "blasphemy",
        "blatant", "bleak", "blemish", "blight", "bliss", "blizzard", "bloat",
        "blot", "blunder", "blunt", "blur", "blurt", "blush", "boast", "bode",
        "boggle", "bogus", "boisterous", "bolster", "bombard", "bona fide", "bondage",
        "bonnet", "bonus", "boom", "boost", "boot", "booth", "borderline", "bore",
        "borough", "bosom", "botany", "bounty", "bouquet", "bourgeois", "bout",
        "boycott", "brace", "bracket", "brag", "braid", "bramble", "brandish",
        "bravado", "brawl", "breach", "breadth", "brevity", "bribe", "bridle",
        "brink", "brisk", "brittle", "broach", "brochure", "broken", "brood",
        "brook", "brow", "browse", "brunt", "brusque", "brute", "buck", "buckle",
        "buddy", "budge", "budget", "buffet", "buggy", "bulge", "bulk", "bulky",
        "bull", "bulletin", "bully", "bump", "bunch", "bundle", "bunker", "buoy",
        "buoyant", "burden", "bureau", "burglar", "burial", "burly", "burrow",
        "bursar", "burst", "bushel", "bustle", "butt", "butter", "bypass", "cabin",
        "cable", "cadaver", "cadence", "cadet", "cajole", "calamity", "calcium",
        "caliber", "calibrate", "callous", "callow", "calorie", "cameo", "campaign",
        "canary", "candid", "candidate", "candor", "candy", "canine", "canopy",
        "canteen", "canyon", "capable", "capacity", "capillary", "capitulate",
        "caprice", "capsule", "caption", "captive", "capture", "carat", "carbohydrate",
        "carbon", "cardinal", "career", "carefree", "caress", "cargo", "caricature",
        "carnage", "carnival", "carp", "carpet", "carriage", "cartel", "cartridge",
        "cascade", "caste", "casualty", "catalyst", "cataract", "catastrophe",
        "categorical", "cater", "cathedral", "cattle", "caucus", "causal", "cause",
        "caustic", "caution", "cavalry", "caveat", "cease", "cedar", "censor",
        "censure", "census", "centenary", "centigrade", "centralize", "ceramic",
        "cereal", "ceremonial", "certainty", "certificate", "certify", "cessation",
        "chagrin", "chairman", "chalk", "challenge", "chamber", "champion", "chaos",
        "character", "characteristic", "charge", "charisma", "charm", "charter",
        "chassis", "chaste", "chatter", "check", "cheek", "cheer", "cherish",
        "chicane", "chide", "chief", "chimpanzee", "chip", "chirp", "chisel",
        "choir", "chord", "chore", "chorus", "chronic", "chuck", "chuckle", "churn",
        "cilantro", "cipher", "circulate", "circumference", "circumlocution",
        "circumscribe", "circumvent", "citation", "cite", "civic", "civilian",
        "claim", "clairvoyant", "clamber", "clammy", "clang", "clap", "clarify",
        "clarity", "clash", "clasp", "classify", "clatter", "clause", "claw",
        "cleave", "cleft", "clergy", "cliché", "clientele", "climactic", "climb",
        "clinch", "cling", "clinic", "clip", "cloak", "clog", "cloister", "clone",
        "clout", "clumsy", "cluster", "clutch", "clutter", "coalesce", "coarse",
        "coax", "cobalt", "cobra", "cocaine", "cocoa", "coconut", "cocoon", "codify",
        "coerce", "coexist", "cogent", "cognitive", "cognizant", "cohere", "cohesion",
        "cohort", "coil", "coinage", "coincide", "colander", "cold", "collaborate",
        "collapse", "colleague", "collect", "collegiate", "collide", "collision",
        "colloquial", "collusion", "colon", "colonel", "colonial", "colossal",
        "columnist", "coma", "combat", "combustion", "comely", "comet", "comfort",
        "comic", "commander", "commemorate", "commence", "commend", "commentary",
        "commerce", "commingle", "commission", "commit", "committee", "commodity",
        "commonplace", "commonsense", "commotion", "commune", "communicate",
        "commute", "compact", "comparable", "compatible", "compel", "compensate",
        "compete", "compile", "complacent", "complain", "complement", "complex",
        "complicate", "compliment", "comply", "component", "compose", "composure",
        "compound", "comprehend", "compress", "comprise", "compromise", "compulsory",
        "compunction", "conceal", "concede", "conceive", "concentrate", "concept",
        "concern", "concerted", "concerto", "concise", "conclude", "concoct",
        "concord", "concrete", "concur", "condemn", "condense", "condescend",
        "condition", "condolence", "condone", "conducive", "conduct", "confederate",
        "confer", "confess", "confide", "confident", "confidential", "configuration",
        "confine", "confirm", "conflict", "conform", "confound", "confront",
        "confuse", "congeal", "congenial", "congest", "conglomerate", "congratulate",
        "congregate", "congress", "conjecture", "conjure", "connect", "connive",
        "conscience", "conscious", "consecutive", "consensus", "consent", "consequence",
        "conserve", "consider", "consign", "consist", "console", "consolidate",
        "consonant", "conspicuous", "conspire", "constant", "constellation", "constitute",
        "constrain", "construct", "consult", "consume", "contact", "contagious",
        "contain", "contaminate", "contemplate", "contemporary", "contempt",
        "contend", "content", "contest", "context", "continent", "contingent",
        "continue", "contort", "contract", "contradict", "contrary", "contrast",
        "contravene", "contribute", "contrive", "control", "controversial", "convene",
        "convenient", "convention", "converge", "conversant", "converse", "conversion",
        "convert", "convex", "convey", "convict", "convince", "convivial", "convoy",
        "convulse", "coo", "cookie", "cool", "coordinate", "cope", "copious",
        "cordial", "cordon", "cornerstone", "corollary", "corporate", "corporeal",
        "corps", "corpse", "corpus", "corral", "corrode", "corrupt", "cosmetic",
        "cosmic", "cosmos", "cosset", "costume", "coterie", "cottage", "couch",
        "council", "counsel", "countenance", "counter", "counterfeit", "counterpart",
        "coup", "couple", "coupon", "courageous", "course", "court", "courteous",
        "covenant", "cover", "covet", "cow", "coward", "cozy", "crab", "crack",
        "cradle", "craft", "cram", "cramp", "crane", "cranky", "crave", "craw",
        "crayon", "crazed", "creak", "cream", "crease", "create", "credential",
        "credible", "credit", "creed", "creek", "creep", "cremate", "crescent",
        "crest", "crevice", "crew", "crib", "cricket", "crime", "crimson", "cringe",
        "crisis", "crisp", "criteria", "critic", "critical", "critique", "croak",
        "crochet", "crock", "crook", "croon", "cross", "crouch", "crowd", "crown",
        "crucial", "crude", "cruel", "cruise", "crusade", "crush", "crust", "cry",
        "cryptic", "crystal", "cub", "cuddle", "cuisine", "culminate", "culpable",
        "cultivate", "culture", "cumbersome", "cumulative", "cunning", "cupboard",
        "curb", "cure", "curfew", "curio", "curl", "currency", "current", "curriculum",
        "curry", "curse", "cursory", "curt", "curtain", "curve", "cushion", "cusp",
        "custody", "customary", "customer", "cut", "cute", "cutlery", "cyclone",
        "cylinder",
    ],
}


def _search_github_for_cet_files(
    scraper: BaseScraper, level: str
) -> list[tuple[str, str]]:
    """Use GitHub Code Search to find public JSON/TXT CET word lists.

    Note: unauthenticated requests are rate-limited to 10/min; we
    only make one call per level to keep noise low.
    """
    key_term = "cet4" if level == "CET4" else "cet6"
    params = {
        "q": f"{key_term} extension:json OR extension:txt in:path",
        "per_page": "15",
    }
    # Custom Accept header for code search preview
    data = scraper.get_json(
        GITHUB_SEARCH_API, params=params,
        headers={"Accept": "application/vnd.github.text-match+json"},
    )
    if not data or "items" not in data:
        return []
    out: list[tuple[str, str]] = []
    for item in data["items"]:
        repo = item.get("repository", {})
        owner = repo.get("owner", {}).get("login", "")
        name = repo.get("name", "")
        path = item.get("path", "")
        if not (owner and name and path):
            continue
        # Build the raw.githubusercontent.com URL for the default branch
        # (try "main" first, fall back to "master" later)
        url = f"https://raw.githubusercontent.com/{owner}/{name}/main/{path}"
        out.append((url, "json" if path.endswith(".json") else "text"))
    return out


def _parse_json_words(data: object) -> list[dict]:
    """Normalize many JSON shapes into a list of dicts with at least ``word``."""
    out: list[dict] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                out.append({"word": item.strip()})
            elif isinstance(item, dict):
                w = item.get("word") or item.get("name") or item.get("term")
                if w:
                    out.append({"word": str(w).strip(), "raw": item})
    elif isinstance(data, dict):
        # Some lists are dicts of {word: definition}
        for k, v in data.items():
            if isinstance(v, str):
                out.append({"word": k, "translation": v})
            elif isinstance(v, dict):
                out.append({"word": k, "raw": v})
    return out


def _parse_text_words(text: str) -> list[dict]:
    """One word per line / comma-separated."""
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Skip "1. apple" style numbering
        line = re.sub(r"^\d+[\.\)]\s*", "", line)
        # Skip "apple 苹果" (tab-separated)
        parts = re.split(r"\s+|\t|,|;", line, maxsplit=1)
        if not parts or not parts[0]:
            continue
        word = re.sub(r"[^A-Za-z\-']", "", parts[0]).lower()
        if 2 <= len(word) <= 30:
            entry = {"word": word}
            if len(parts) > 1:
                entry["translation"] = parts[1].strip()
            out.append(entry)
    return out


def _try_master_branch(base_url: str) -> str:
    """Convert /main/ to /master/ in raw.githubusercontent URLs."""
    return base_url.replace("/main/", "/master/", 1)


def fetch(scraper: BaseScraper) -> Iterator[RawItem]:
    """Yield vocab RawItems from any working source."""
    for level, urls in CANDIDATES:
        # Build the full URL list: curated + GitHub search results.
        candidate_urls = list(urls)
        try:
            extra = _search_github_for_cet_files(scraper, level)
            for u, fmt in extra:
                if (u, fmt) not in candidate_urls:
                    candidate_urls.append((u, fmt))
            if extra:
                log.info(f"  GitHub code search: {len(extra)} extra candidates for {level}")
        except Exception as e:  # noqa: BLE001
            log.warning(f"  GitHub search failed: {e}")

        got = False
        for url, fmt in candidate_urls:
            log.info(f"  trying {url}")
            data: object | None = None
            if fmt == "json":
                data = scraper.get_json(url)
                if data is None:
                    data = scraper.get_json(_try_master_branch(url))
            else:
                text = scraper.get_text(url)
                if text is None:
                    text = scraper.get_text(_try_master_branch(url))
                if text is not None:
                    data = text  # type: ignore[assignment]
            if data is None:
                continue
            if fmt == "json":
                items = _parse_json_words(data)
            else:
                items = _parse_text_words(data)  # type: ignore[arg-type]
            if not items:
                continue
            log.info(f"    ✓ pulled {len(items)} words for {level} from {url}")
            for entry in items:
                yield RawItem(
                    source="github",
                    section="vocabulary",
                    level=level,
                    payload=entry,
                )
            got = True
            break
        if not got:
            log.warning(f"  no GitHub source worked for {level}, using local fallback list")
            for w in FALLBACK_WORDS.get(level, []):
                yield RawItem(
                    source="fallback-list",
                    section="vocabulary",
                    level=level,
                    payload={"word": w, "translation": "", "tags": "本地兜底词表"},
                )
