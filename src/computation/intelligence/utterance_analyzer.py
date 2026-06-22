
from __future__ import annotations
import re

_COMMAND_RE_STRINGS: list[str] = [

    r"\bplay\b",
    r"\bpause\b",
    r"\bstop\b",
    r"\bresume\b",
    r"\bskip\b",
    r"\bnext\s+(song|track|episode|video|chapter)\b",
    r"\b(previous|prev|go\s+back)\s+(song|track|episode)\b",
    r"\bvolume\s+(up|down)\b",
    r"\blouder\b",
    r"\bquieter\b",
    r"\bmute\b",
    r"\bunmute\b",
    r"\bshuffle\b",
    r"\brepeat\b",
    r"\bfast\s*forward\b",
    r"\brewind\b",
    r"\bstart\s+(the\s+)?music\b",

    r"\bturn\s+(it\s+)?(on|off)\b",
    r"\bswitch\s+(it\s+)?(on|off)\b",
    r"\bpower\s+(it\s+)?(on|off)\b",
    r"\benable\b",
    r"\bdisable\b",
    r"\bactivate\b",
    r"\bdeactivate\b",

    r"\bdim\b",
    r"\bbrighten\b",
    r"\bturn\s+(on|off)\s+(the\s+)?lights?\b",
    r"\blights?\s+off\b",
    r"\b(turn|switch|put)\s+(on|off)\s+(the\s+)?lights?\b",
    r"\bset\s+(the\s+)?(lights?|brightness|lamp)\b",
    r"\bchange\s+(the\s+)?(lights?|color|bulb)\b",
    r"\bswitch\s+(to\s+)?(night\s+light|reading\s+mode|movie\s+mode)\b",
    r"\bset\s+(the\s+)?color\b",
    r"\bcolou?r\s+the\s+lights?\b",

    r"\bset\s+(the\s+)?(thermostat|temperature|ac|air\s+conditioning|heater|heat|fan|humidity)\b",
    r"\bmake\s+it\s+(warmer|cooler|hotter|colder)\b",
    r"\bturn\s+(on|off)\s+(the\s+)?(ac|air\s+conditioning|heater|heat|fan|radiator|humidifier|dehumidifier)\b",
    r"\bincrease\s+(the\s+)?(temperature|heat|warmth)\b",
    r"\bdecrease\s+(the\s+)?(temperature|cooling)\b",
    r"\bcrank\s+(up|down)\s+the\s+(ac|heat|fan)\b",
    r"\bset\s+.{1,30}\s+degrees?\b",
    r"\b(warmer|cooler)\s+in\s+here\b",

    r"\block\s+(the\s+)?(door|house|home|garage|front|back|bedroom|car)\b",
    r"\bunlock\s+(the\s+)?(door|house|home|garage|front|back|bedroom|car)\b",
    r"\barm\s+(the\s+)?(alarm|security|system)\b",
    r"\bdisarm\s+(the\s+)?(alarm|security|system)\b",
    r"\bcheck\s+(the\s+)?(cameras?|security|locks?|doors?|windows?)\b",
    r"\bshow\s+(me\s+)?(the\s+)?(cameras?|front\s+door|doorbell|feed)\b",
    r"\bsecure\s+(the\s+)?(house|home|property|perimeter)\b",
    r"\bopen\s+(the\s+)?(gate|garage\s+door|front\s+door|security\s+door)\b",

    r"\bstart\s+(the\s+)?(washer|dryer|dishwasher|oven|microwave|coffee\s+maker|robot|roomba|vacuum|blender)\b",
    r"\bstop\s+(the\s+)?(washer|dryer|dishwasher|oven|microwave|coffee\s+maker|robot|roomba|vacuum)\b",
    r"\bturn\s+(on|off)\s+(the\s+)?(washer|dryer|dishwasher|oven|microwave|coffee\s+maker|tv|television|laptop|computer|printer|iron|kettle)\b",
    r"\bpreheat\s+(the\s+)?oven\b",
    r"\brun\s+(a\s+)?(wash\s+cycle|dishwasher\s+cycle|cycle)\b",
    r"\bbrew\s+(a\s+)?(coffee|cup|pot)\b",
    r"\bboil\s+(some\s+)?water\b",
    r"\bmicrowave\s+(for\s+)?\d+\s+(seconds?|minutes?)\b",

    r"\bput\s+on\s+(a\s+)?(movie|show|episode|series)\b",
    r"\bwatch\b",
    r"\bstream\b",
    r"\bswitch\s+to\s+(netflix|youtube|spotify|hulu|disney(\+)?|prime|hbo|apple\s+tv)\b",
    r"\bopen\s+(netflix|youtube|spotify|hulu|disney(\+)?|prime|hbo)\b",
    r"\bsearch\s+(netflix|youtube|spotify)\s+for\b",
    r"\bfind\s+(a\s+)?(movie|show|song|playlist|artist|album|documentary)\b",

    r"\bcall\s+(mom|dad|home|work|office|\w+\s+at|my\s+\w+)\b",
    r"\b(call|dial)\s+\d",
    r"\bplace\s+a\s+(call|phone\s+call)\b",
    r"\bdial\b",
    r"\btext\b",
    r"\bsend\s+(a\s+)?(text|message|voice\s+message)\b",
    r"\bemail\b",
    r"\bsend\s+an?\s+(email|message)\b",
    r"\bread\s+(my\s+)?(messages?|emails?|texts?|notifications?|voicemails?)\b",
    r"\breply\b",
    r"\bvideo\s+(call|chat)\b",
    r"\bfaceTime\b",
    r"\bwhatsapp\b",

    r"\border\s+(a|an|some|food|pizza|groceries|takeaway|takeout|delivery)\b",
    r"\border\s+from\b",
    r"\bbuy\s+(a|an|some|more)\b",
    r"\bpurchase\b",
    r"\badd\s+.{1,40}\s+to\s+(my\s+)?(shopping|grocery|to-?do|wish)?\s*list\b",
    r"\bremove\s+.{1,30}\s+from\s+(my\s+)?list\b",
    r"\bplace\s+an?\s+order\b",
    r"\breorder\b",
    r"\bcheck\s+out\b",
    r"\badd\s+to\s+(my\s+)?cart\b",

    r"\bset\s+(a\s+)?(timer|alarm|countdown|reminder)\b",
    r"\bremind\s+me\b",
    r"\bwake\s+me\s+up\b",
    r"\bschedule\s+(a|an|the)?\b",
    r"\bcancel\s+(the\s+)?(timer|alarm|reminder)\b",
    r"\bsnooze\b",
    r"\bstart\s+(a\s+)?(timer|countdown)\b",
    r"\bstop\s+(the\s+)?timer\b",
    r"\bset\s+(an?\s+)?alarm\s+for\b",

    r"\bnavigate\s+to\b",
    r"\bdirections?\s+to\b",
    r"\btake\s+me\s+to\b",
    r"\bget\s+me\s+to\b",
    r"\bgo\s+to\b",
    r"\bshow\s+me\s+the\s+way\s+to\b",
    r"\bstart\s+(the\s+)?navigation\b",
    r"\bcheck\s+(traffic|commute|route)\b",

    r"\blook\s+up\b",
    r"\bshow\s+me\b",
    r"\btell\s+me\b",
    r"\bgoogle\b",
    r"\bwikipedia\b",
    r"\bdefine\b",
    r"\btranslate\b",
    r"\bconvert\b",
    r"\bcalculate\b",

    r"\bincrease\b",
    r"\bdecrease\b",
    r"\bturn\s+it\s+(up|down)\b",
    r"\bmax(imum)?\s+(volume|brightness|speed)\b",
    r"\bmin(imum)?\s+(volume|brightness|speed)\b",
    r"\bfull\s+volume\b",

    r"\bopen\s+(the\s+)?(door|garage|window|app|curtains?|blinds?|shutters?|sunroof)\b",
    r"\bclose\s+(the\s+)?(door|garage|window|app|curtains?|blinds?|shutters?)\b",
    r"\bshut\s+(the\s+)?(door|window|curtains?|blinds?|garage)\b",
    r"\bdraw\s+(the\s+)?curtains?\b",
    r"\broll\s+(up|down)\s+(the\s+)?blinds?\b",

    r"\bgood\s+morning\s+(mode|routine|scene)?\b",
    r"\bbedtime\s+(mode|routine|scene)?\b",
    r"\bleave\s+(home|house)\s+(mode|scene)?\b",
    r"\barrive\s+(home|house)\b",
    r"\bnight\s+(mode|light|scene)\b",
    r"\bvacation\s+mode\b",
    r"\bguest\s+mode\b",
    r"\bdo\s+not\s+disturb\b",
    r"\bparty\s+mode\b",
    r"\bwork\s+from\s+home\s+(mode|scene)?\b",
    r"\bsleep\s+(mode|scene)\b",
    r"\bcinema\s+(mode|scene)\b",
    r"\bdinner\s+(mode|scene)\b",
    r"\bmorning\s+(routine|scene)\b",
    r"\bevening\s+(routine|scene)\b",
    r"\bwake\s+up\s+(mode|routine)\b",

    r"\bstart\s+(a\s+)?(workout|meditation|yoga|exercise|run|walk)\b",
    r"\btrack\s+(my\s+)?(steps|calories|sleep|heart\s+rate|weight|water)\b",
    r"\blog\s+(my\s+)?(meal|calories|workout|medicine)\b",
    r"\btake\s+(my\s+)?(medicine|medication|pills?|vitamins?)\b",

    r"\braise\b",
    r"\blower\b",

    r"\blisten\s+to\s+(me|my\s+voice)\b",
    r"\b(is\s+)?sen[td]\s+to\s+me\b",
    r"\blisten(ed|ing)?\s+to\s+me\b",
    r"\b(don't|dont)\s+listen\s+to\s+(him|her|them)\b",
    r"\b(don't|dont)\s+listen\b",
    r"\bignore\s+(him|her|them)\b",
    r"\bpay\s+attention\b",
    r"\bfocus\s+on\s+me\b",
    r"\btalk\s+to\s+me\b",
    r"\bspeak\s+to\s+me\b",
    r"\bstop\s+listening\b",
    r"\boverride\b",
]

_WH_WORDS: frozenset[str] = frozenset({
    "what", "where", "when", "who", "whom", "why", "how",
    "which", "whose", "whatever", "wherever", "whenever",
})

_AUX_FIRST_WORDS: frozenset[str] = frozenset({
    "is", "are", "was", "were", "will", "would", "could", "should",
    "can", "do", "does", "did", "has", "have", "had", "am",
    "isn't", "aren't", "wasn't", "weren't", "won't", "wouldn't",
    "couldn't", "shouldn't", "can't", "don't", "doesn't", "didn't",
    "hasn't", "haven't",
})

_COMPILED_CMDS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in _COMMAND_RE_STRINGS
]


def analyze_utterance(text: str) -> dict:
    text = text.strip()
    if not text:
        return {"type": "UNKNOWN", "confidence": 0.0}

    lower      = text.lower()
    first_word = lower.split()[0].rstrip("',?!")

    for pat in _COMPILED_CMDS:
        if pat.search(lower):
            return {"type": "COMMAND", "confidence": 0.95}

    if first_word in _WH_WORDS:
        return {"type": "QUESTION", "confidence": 0.90}

    if first_word in _AUX_FIRST_WORDS:
        return {"type": "QUESTION", "confidence": 0.85}

    if text.rstrip().endswith("?"):
        return {"type": "QUESTION", "confidence": 0.80}

    if len(text.split()) >= 2:
        return {"type": "CONVERSATION", "confidence": 0.75}

    return {"type": "UNKNOWN", "confidence": 0.40}
