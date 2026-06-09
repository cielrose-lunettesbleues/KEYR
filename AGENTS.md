# AGENTS.md

## Scope et langue
- Langue de travail: francais.
- Projet: pipeline local Twitch VOD OBS (`.mp4`) -> shorts verticaux + integration DaVinci Resolve.

## Commandes fiables (Windows)
- Lancer un batch: `py -3 -m short_editor.cli run-batch --config config/pipeline.json`
- Appliquer feedback: `py -3 -m short_editor.cli learn --config config/pipeline.json --feedback feedback/latest_feedback.csv`
- Wrappers equivalents: `run_shorts.bat`, `learn_shorts.bat` (minuscules dans ce repo).
- Installer le script Resolve: `INSTALL_RESOLVE_SCRIPT.bat` (copie vers `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility`).

## Verifications rapides apres modif
- Check syntax Python ciblee: `py -3 -m py_compile resolve_integration/run_shorts_batch_resolve.py`
- Si modif pipeline CLI: lancer `run-batch` sur `config/pipeline.json` et verifier JSON de sortie + `output/manifests/*.json`.
- Si modif notation/learn: verifier creation de `feedback/latest_feedback.csv`, `feedback/history/*.csv` et `config/transcript_lexicon_user.json`.

## Architecture reelle (points d'entree)
- CLI unique: `short_editor/cli.py` (`run-batch`, `learn`).
- Orchestration batch: `short_editor/pipeline.py`.
- Manifests batch/Resolve: `short_editor/manifest_builder.py`.
- Chapitres/quota: `short_editor/chapters.py`.
- Selection clips auto: `short_editor/fallback.py`.
- Analyse audio: `short_editor/audio_analysis.py`.
- Trim dead-air: `short_editor/trimming.py`.
- Render ffmpeg: `short_editor/render.py`.
- Transcription locale: `short_editor/transcription.py` (faster-whisper).
- Sous-titres Text+ Resolve: `short_editor/captions.py` genere des segments en memoire depuis transcript, sans `.srt`.
- Feedback + lexique user: `short_editor/feedback.py`.
- UI Resolve + generation manifest auto: `resolve_integration/run_shorts_batch_resolve.py`.
- Helpers Resolve: `resolve_integration/resolve_app/` (`api`, `logging`, `paths`, `presets`, `manifests`, `plans`, `media_pool`, `timelines`, `transforms`, `selected_clip`, `render_queue`, `textplus`, `project_settings`, `optimized_media`).
- Presets Resolve persistes dans `config/resolve_presets.json`.

## Regles metier a ne pas casser
- Ignorer toujours le chapitre index 0 / `start_seconds == 0`.
- Toujours inclure les clips de chapitres valides, puis completer le quota via fallback si insuffisant.
- Cible quota: `2.5/h` (min `2`, max `3`) avec overflow autorise (`config/pipeline.json`).
- Cible video: `1080x1920`, `60 fps`, `max_clip_seconds` 60 (pipeline) et 45s pour clips filtres par requete transcript/presets.
- Nommage utilisateur simple attendu: `Chapitre N` et `Auto N`.

## Audio: conventions specifiques repo
- Spotify doit rester mute (track OBS 4 via `audio.always_muted_tracks`).
- Analyse vocale principale: track 2; contexte: track 5; render base: track 6 (`config/pipeline.json`).
- `render.py` peut auto-selectionner une autre piste si plus audible; cela genere un warning normal (ne pas traiter comme crash).

## Resolve/UI: contraintes importantes
- Script pense pour Resolve Studio 20 beta, projet deja ouvert.
- Mapping detect preset impose: `Track1 = camera`, `Track2 = gameplay`.
- L'UI conserve une fenetre unique, preset editor compact, et supporte `Update Composition (Batch)` sans regeneration complete.
- Le texte `(... N warnings)` dans la barre de statut est cliquable et ouvre le detail warnings.
- Boutons generation: `Generate Batch (Fast)` et `Generate + Auto Subtitles (Quality)`.
- Bouton `Load Current` est en haut, a cote du selecteur de preset (hors zone minimisable).
- Fenetre `Noter le batch`:
  - ouverture auto apres generation reussie,
  - rouvrable via bouton `Noter le batch`,
  - notes 1..5 etoiles (non note = neutre 3),
  - affichage noms timeline et mots transcript (`matched=...`).
- Loader Kirby:
  - affiche etape courante + pourcentage,
  - barre de progression custom Canvas (pas ttk Progressbar),
  - picker VOD parent au loader pour eviter conflit de fenetres.

## Sous-titres (etat actuel)
- Mode cible: clips Text+ editables en timeline Resolve.
- Moteur: `faster-whisper` local (`config/pipeline.json > captions.engine`).
- Mode Quality genere/reutilise le transcript puis applique le template Text+ Resolve directement.
- Aucun fichier `.srt` ni champ `subtitle_path` dans le flux actif.

## Selection clips fallback (etat actuel)
- Chapitres valides priorite absolue.
- Completion quota via fallback multi-pass:
  - transcript strict,
  - transcript assoupli,
  - safety net audio,
  - puis selection anti-overlap (passe stricte puis relaxee).

## Logs, artefacts, diagnostics
- Log principal Resolve: `C:\Users\untho\Desktop\short_editor_resolve.log`.
- Manifests batch: `output/manifests/`.
- Clips rendus: `output/clips/<batch_id>/`.
- Index review principal: `output/reports/<batch_id>.review.csv`.
- Transcripts: `output/transcripts/<vod_stem>.json`.
- Feedback ratings: `feedback/latest_feedback.csv` et `feedback/history/`.
- Lexique learn user: `config/transcript_lexicon_user.json`.

## Gotchas verifies
- Les assets GIF Kirby sont requis pour le loader anime (`resolve_integration/assets/kirby_*.gif`); fallback texte existe si manquants.
- Ne pas renommer les scripts `.bat` en majuscules dans la doc interne: les noms presents sont `run_shorts.bat` / `learn_shorts.bat`.
