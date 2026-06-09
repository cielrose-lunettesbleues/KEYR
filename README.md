# Short Editor

Pipeline local pour transformer des VOD Twitch/OBS `.mp4` en shorts verticaux et les assembler dans DaVinci Resolve.

## Features Conservées

- Détection des chapitres OBS, avec exclusion systématique du chapitre `0` / `start_seconds == 0`.
- Inclusion prioritaire des chapitres valides.
- Complément automatique avec clips `Auto N` quand les chapitres ne suffisent pas au quota.
- Sélection auto multi-pass basée sur transcript, énergie audio, hook et anti-overlap.
- Rendu local ffmpeg vertical `1080x1920 @ 60fps` pour review CLI.
- Intégration DaVinci Resolve avec une timeline par clip et une timeline `MASTER_REVIEW`.
- Réouverture de session: si une VOD sélectionnée possède déjà un manifest, le script propose de le rouvrir.
- Génération initiale de manifest sans transcript au lancement Resolve.
- Mode `Generate + Auto Subtitles (Quality)` qui génère le transcript à la demande puis applique les sous-titres via Text+ Resolve.
- Feedback de batch et apprentissage du lexique utilisateur.

## Sous-Titres

Les sous-titres ne sont plus exportés en fichiers `.srt`.

Le flux actuel est:

```text
VOD -> transcript JSON faster-whisper -> segments en mémoire -> template Text+ Resolve
```

Le template Resolve est fourni par `resolve_integration/assets/shorteditor-caption-bin.drb`. Si l'application Text+ échoue, le script remonte un warning; il ne génère pas de fallback SRT.

## Installation

1. Installer Python 3.11+.
2. Installer `ffmpeg` et `ffprobe` dans le `PATH`.
3. Installer `faster-whisper` pour les transcripts utilisés par les clips auto et les sous-titres Text+.
4. Pour Resolve, installer le script:

```bat
.\INSTALL_RESOLVE_SCRIPT.bat
```

## Utilisation CLI

Lancer un batch local:

```bat
py -3 -m short_editor.cli run-batch --config config\pipeline.json
```

Ou:

```bat
.\run_shorts.bat
```

Appliquer le feedback:

```bat
py -3 -m short_editor.cli learn --config config\pipeline.json --feedback feedback\latest_feedback.csv
```

Ou:

```bat
.\learn_shorts.bat
```

## Utilisation Resolve

1. Ouvrir un projet DaVinci Resolve.
2. Sélectionner une VOD dans la timeline ou le Media Pool si possible.
3. Lancer `Workspace -> Scripts -> Utility -> run_shorts_batch_resolve`.
4. Si aucune VOD n'est détectée, le script propose d'en sélectionner une.
5. Si un manifest existe déjà pour la VOD, le script propose de rouvrir la session.
6. Sinon, un manifest frais est généré sans transcript.
7. Dans l'UI, utiliser `Generate Batch (Fast)` ou `Generate + Auto Subtitles (Quality)`.

## Structure

- `short_editor/`: pipeline Python principal, selection clips, manifests, captions Text+ et analyse audio.
- `resolve_integration/run_shorts_batch_resolve.py`: point d'entree installe dans Resolve.
- `resolve_integration/resolve_app/`: modules Resolve extraits (`api`, `paths`, `presets`, `manifests`, `logging`).
- `resolve_integration/assets/`: template Text+ et assets UI.
- `config/`: configuration pipeline, presets Resolve et lexique utilisateur.
- `input/`: VOD sources pour le mode CLI.
- `output/`: manifests, clips rendus, transcripts et rapports générés.
- `feedback/`: feedback courant et historique.
- `archive/`: ancien code conservé hors application.
- `tests/`: tests unitaires sans Resolve.

## Vérification Rapide

```bat
py -3 -m py_compile short_editor\*.py resolve_integration\run_shorts_batch_resolve.py
```

Si des tests sont présents:

```bat
py -3 -m unittest discover -s tests
```
