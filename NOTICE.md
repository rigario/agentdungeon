# NOTICE / Credits

AgentDungeon / The Dreaming Hunger is an original human-agent co-play RPG prototype by the AgentDungeon contributors.

This file is intended to keep required credits visible in the repository. It is not legal advice.

## Project code and original content

- **Project:** AgentDungeon / The Dreaming Hunger
- **Repository:** https://github.com/rigario/agentdungeon
- **License for original project code:** MIT License; see `LICENSE`.
- **Original campaign material:** Thornhold, The Dreaming Hunger campaign frame, original NPCs, locations, items, UI copy, generated art direction, and portal/agent-play workflows are project-original unless a file states otherwise.

## Dungeons & Dragons System Reference Document

AgentDungeon is a 5E-compatible project. Where it uses or adapts rules terms, classes, species/races, mechanics, spells, equipment, or other reference material from the Dungeons & Dragons System Reference Document, that material is credited as follows:

- **Source:** System Reference Document v5.2.1 and/or SRD v5.1 materials published by Wizards of the Coast LLC.
- **Publisher:** Wizards of the Coast LLC.
- **Source URL:** https://www.dndbeyond.com/srd
- **License:** Creative Commons Attribution 4.0 International, https://creativecommons.org/licenses/by/4.0/
- **Changes:** SRD concepts may be represented as software validation, API schemas, seed data, UI labels, gameplay traces, and campaign-specific presentation. AgentDungeon adds original campaign setting, agent workflow, persistence, portal UI, and narration layers.

This project is not affiliated with, endorsed, sponsored, or specifically approved by Wizards of the Coast LLC. Dungeons & Dragons and related marks are trademarks of Wizards of the Coast LLC.

## Runtime, framework, and tool credits

AgentDungeon depends on third-party open-source software packages. They are not vendored here unless explicitly present in the repository. Primary runtime/framework packages include:

- FastAPI
- Uvicorn
- Pydantic
- HTTPX
- Redis Python client
- APScheduler
- Authlib
- cryptography
- pytest / pytest-asyncio / pytest-xdist for development and tests

Each dependency remains under its own license. Review installed package metadata or upstream repositories for exact license text when redistributing dependency bundles or container images.

## Fonts

The public website and portal use web fonts served through Google Fonts, including some or all of:

- Cinzel
- Spectral
- Source Sans 3
- Bitter
- Crimson Text
- Fira Code

These font families are distributed by their respective authors under their own font licenses, commonly the SIL Open Font License for Google Fonts families. The fonts are loaded from Google Fonts rather than vendored in this repository unless a specific font file is later committed with its own license notice.

## Generated / project-created media

Pixel-art images, generated character/location/item/NPC assets, demo imagery, and ambient audio in this project are project-created assets unless a file states otherwise. Some assets were created with AI-assisted generation and then edited/conformed for the AgentDungeon art direction. They should not be interpreted as official Dungeons & Dragons artwork or as artwork endorsed by any third party.

If an asset is later replaced with third-party art, icons, music, sound effects, screenshots, or stock material, add that asset's source, creator, license, and required attribution here before publishing.

## Attribution hygiene for contributors

Before adding external material:

1. Confirm the license allows this use.
2. Avoid GPL/AGPL/strong-copyleft assets or code unless the whole project intentionally adopts those terms.
3. Prefer MIT, Apache-2.0, BSD, ISC, CC0, or CC-BY material.
4. Add the source, author, license, source URL, and modification note to this file.
5. If the material appears on the public website, make sure `/credits` or the relevant page also exposes the credit.
