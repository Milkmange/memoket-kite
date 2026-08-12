"""Prompt templates for natural-language retrieval-plan compilation."""

DEFAULT_COMPILE_PROMPT = """Translate the question into a KITE retrieval plan. Return JSON only.
TOPICS: {tree}
ENTITIES: {entities}
KINDS: {kinds}
UNITS: {units}
TODAY: {today}
QUESTION: {question}
Use one to three queries. Include a broad fact grep query using distinctive word stems.
Schema: {{"queries":[{{"select":"facts","where":{{"grep":str,"who":[str],
"topics":[{{"code":str,"closure":true}}],"entities":[str],"kind":[str],
"time":[str,str]}},"pipe":[{{"op":"head","n":10}}]}}],"intent":"factual"}}"""
