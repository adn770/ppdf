#!/usr/bin/env python3
"""
ppdf: An advanced PDF text and structure extraction tool.

This script provides a comprehensive solution for extracting, understanding, and
reformatting content from PDF files. It uses a multi-stage analysis pipeline
(handled by the PDFTextExtractor class) to identify the document's logical
structure and an LLM to produce a clean, readable Markdown file.
"""

import argparse
import json
import logging
import os
import sys
import time

# --- Dependency Imports ---
try:
    import requests
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
except ImportError as e:
    print(f"Error: Missing required library. -> {e}")
    print("Please install all core dependencies with:")
    print("pip install requests rich")
    sys.exit(1)

# --- Local Application Imports ---
from core.constants import PROMPT_PRESETS
from core.extractor import PDFTextExtractor
from core.tts import TTSManager, PIPER_AVAILABLE
from core.utils import ASCIIRenderer, RichLogFormatter


# --- LOGGING SETUP ---
log_llm = logging.getLogger("ppdf.llm")


class Application:
    """Orchestrates the PDF processing workflow based on command-line arguments."""
    DEFAULT_FILENAME_SENTINEL = "__DEFAULT_FILENAME__"
    DEFAULT_CHUNK_SIZE = 4000

    def __init__(self, args):
        self.args = args
        self.stats = {}
        self.extractor = PDFTextExtractor(
            args.pdf_file, args.columns, args.remove_footers, args.keep_style
        )
        self.tts_manager = None

    def run(self):
        """Main entry point for the application logic."""
        self.stats['start_time'] = time.monotonic()
        self._configure_logging()

        try:
            if self.args.batch_presets:
                presets_to_run = list(PROMPT_PRESETS.keys())
            else:
                presets_to_run = [self.args.prompt_preset]

            context_size = self._get_model_details()
            if context_size and self.args.chunk_size == self.DEFAULT_CHUNK_SIZE:
                self.args.chunk_size = int(context_size * 0.8)
                logging.getLogger("ppdf").info(
                    "Auto-adjusting chunk size to %d.", self.args.chunk_size
                )

            pages = self._parse_page_selection()
            if pages is None and self.args.pages.lower() != 'all':
                sys.exit(1)

            pdf_start = time.monotonic()
            sections = self.extractor.extract_sections(pages)
            self.stats['pdf_analysis_duration'] = time.monotonic() - pdf_start
            self.stats['pages_processed'] = len(self.extractor.page_models)
            self.stats['sections_reconstructed'] = len(sections)

            if not sections:
                logging.getLogger("ppdf").error(
                    "No content could be extracted. Exiting."
                )
                self._display_performance_epilogue(self.stats, "N/A")
                return

            for preset in presets_to_run:
                self._run_for_preset(preset, sections)

        except Exception as e:
            logging.getLogger("ppdf").critical(
                "\nAn unexpected error occurred: %s", e, exc_info=True
            )
            if self.tts_manager:
                self.tts_manager.cleanup()
            sys.exit(1)

    def _run_for_preset(self, preset_name, sections):
        """Executes the processing pipeline for a single prompt preset."""
        run_stats = {'start_time': time.monotonic()}
        original_output = self.args.output_file
        original_extracted = self.args.extracted_file

        if self.args.batch_presets:
            logging.getLogger("ppdf").info(
                "\n--- Running Batch Mode: Processing with preset '%s' ---",
                preset_name
            )
            if original_output and original_output != self.DEFAULT_FILENAME_SENTINEL:
                base, ext = os.path.splitext(original_output)
                self.args.output_file = f"{base}_{preset_name}{ext}"
            if original_extracted and original_extracted != self.DEFAULT_FILENAME_SENTINEL:
                base, ext = os.path.splitext(original_extracted)
                self.args.extracted_file = f"{base}_{preset_name}{ext}"

        try:
            self._resolve_output_filenames()
            system_prompt = self._build_system_prompt(PROMPT_PRESETS[preset_name])
            self._log_run_conditions(system_prompt, preset_name)
            self._save_extracted_text(sections)

            if self.args.dry_run:
                self._display_dry_run_summary(sections)
            else:
                if self.args.speak:
                    self._initialize_tts()

                llm_start = time.monotonic()
                final_md = self._generate_output_with_llm(
                    sections, system_prompt, run_stats
                )
                run_stats['llm_wall_duration'] = time.monotonic() - llm_start

                self._save_llm_output(final_md)
        finally:
            if self.tts_manager:
                self.tts_manager.cleanup()
                self.tts_manager = None
            self._display_performance_epilogue(run_stats, preset_name)
            self.args.output_file = original_output
            self.args.extracted_file = original_extracted

    def _initialize_tts(self):
        """Initializes the TTSManager if the --speak flag is used."""
        if not PIPER_AVAILABLE:
            logging.warning(
                "TTS dependencies not installed. --speak flag will be ignored."
            )
            logging.warning(
                'To enable speech, run: pip install "piper-tts==1.3.0" pyaudio'
            )
            self.args.speak = None
            return
        try:
            self.tts_manager = TTSManager(lang=self.args.speak)
            logging.getLogger("ppdf.tts").info(
                "TTS Manager initialized for language: '%s'", self.args.speak
            )
        except Exception as e:
            logging.getLogger("ppdf.tts").error(
                "Failed to initialize TTS Manager: %s", e, exc_info=True
            )
            self.tts_manager = None
            self.args.speak = None

    def _get_model_details(self):
        """Queries the Ollama /api/show endpoint for model details."""
        app_log = logging.getLogger("ppdf")
        app_log.info("Querying details for model: %s...", self.args.model)
        try:
            response = requests.post(
                f"{self.args.url}/api/show", json={"name": self.args.model}
            )
            if response.status_code == 404:
                app_log.error("Model '%s' not found.", self.args.model)
                sys.exit(1)
            response.raise_for_status()
            model_info = response.json()
            details = model_info.get('details', {})
            app_log.info(
                "Ollama Model: Family=%s, Size=%s, Quantization=%s",
                details.get('family', 'N/A'),
                details.get('parameter_size', 'N/A'),
                details.get('quantization_level', 'N/A')
            )
            for line in model_info.get('modelfile', '').split('\n'):
                if 'num_ctx' in line.lower():
                    try:
                        return int(line.split()[1])
                    except (ValueError, IndexError):
                        continue
            return None
        except requests.exceptions.RequestException as e:
            app_log.error("Could not connect to Ollama at %s: %s", self.args.url, e)
            sys.exit(1)

    def _display_performance_epilogue(self, run_stats, preset_name):
        """Displays a summary of performance statistics."""
        app_log = logging.getLogger("ppdf")
        total_dur = time.monotonic() - run_stats.get('start_time', time.monotonic())
        self.stats.update(run_stats)

        eval_dur_s = self.stats.get('llm_eval_duration', 0) / 1e9
        eval_count = self.stats.get('llm_eval_count', 0)
        tps = (eval_count / eval_dur_s) if eval_dur_s > 0 else 0

        report = [
            f"\n--- Performance Epilogue (Preset: {preset_name}) ---",
            f"Total Execution Time: {total_dur:.1f} seconds",
            f"PDF Analysis: {self.stats.get('pdf_analysis_duration', 0):.1f}s "
            f"({self.stats.get('pages_processed',0)} pages, "
            f"{self.stats.get('sections_reconstructed',0)} sections)"
        ]
        if not self.args.dry_run:
            report.extend([
                f"LLM Wall Clock: {self.stats.get('llm_wall_duration', 0):.1f}s",
                f"LLM Generation: {tps:.1f} tokens/sec "
                f"({self.stats.get('llm_eval_count', 0):,} tokens)"
            ])
        app_log.info("\n".join(report))

    def _log_run_conditions(self, system_prompt, preset_name):
        """If debugging is enabled, logs script arguments and system prompt."""
        if self.args.debug_topics:
            args_copy = vars(self.args).copy()
            args_copy['prompt_preset'] = preset_name
            log_llm.debug("--- Script Running Conditions ---\n%s",
                          "\n".join([f"  - {k:<16} : {v}"
                                     for k, v in args_copy.items()]))
        logging.getLogger("ppdf").info(
            "---\nLLM System Prompt (Preset: '%s'):\n%s\n---",
            preset_name, system_prompt
        )

    def _configure_logging(self):
        """Configures logging levels and format based on arguments."""
        level = logging.INFO if self.args.verbose else logging.WARNING
        root_logger = logging.getLogger("ppdf")
        root_logger.setLevel(level)
        if root_logger.hasHandlers():
            root_logger.handlers.clear()
        handler = logging.StreamHandler()
        handler.setFormatter(RichLogFormatter(use_color=self.args.color_logs))
        root_logger.addHandler(handler)
        if self.args.debug_topics:
            root_logger.setLevel(logging.INFO)
            topics = {'layout', 'structure', 'reconstruct', 'llm', 'tts'}
            user_topics = [t.strip() for t in self.args.debug_topics.split(',')]
            to_set = topics if 'all' in user_topics else {
                full for u in user_topics for full in topics if full.startswith(u)
            }
            for topic in to_set:
                logging.getLogger(f"ppdf.{topic}").setLevel(logging.DEBUG)
        logging.getLogger('pdfminer').setLevel(logging.WARNING)

    def _resolve_output_filenames(self):
        """Sets default output filenames based on the input PDF name."""
        S = self.DEFAULT_FILENAME_SENTINEL
        pdf_base = os.path.splitext(os.path.basename(self.args.pdf_file))[0]
        if self.args.output_file == S:
            self.args.output_file = f"{pdf_base}.md"
        if self.args.extracted_file == S:
            self.args.extracted_file = f"{pdf_base}.extracted"

    def _parse_page_selection(self):
        """Parses the --pages argument string (e.g., '1,3,5-7') into a set."""
        if self.args.pages.lower() == 'all':
            return None
        pages = set()
        try:
            for p in self.args.pages.split(','):
                if '-' in p.strip():
                    s, e = map(int, p.strip().split('-'))
                    pages.update(range(s, e + 1))
                else:
                    pages.add(int(p.strip()))
            return pages
        except ValueError:
            logging.getLogger("ppdf").error("Invalid --pages format: %s",
                                            self.args.pages)
            return None

    def _display_dry_run_summary(self, sections):
        """Prints a detailed summary of the extracted document structure."""
        print("\n--- Document Structure Summary (Dry Run) ---")
        print("\n--- Page Layout Analysis ---")
        renderer = ASCIIRenderer(self.extractor)
        for page in self.extractor.page_models:
            print(f"\n[ Page {page.page_num} Layout ]")
            print(renderer.render(page))
        if sections:
            print("\n--- Reconstructed Sections Summary ---")
            for i, s in enumerate(sections):
                print(f"\nSection {i+1}: '{s.title or 'Untitled'}' "
                      f"(Pages: {s.page_start}-{s.page_end})")

    def _save_extracted_text(self, sections):
        """Saves the raw, reconstructed text to a file if requested."""
        if self.args.extracted_file and sections:
            content = [
                f"--- Page {s.page_start}-{s.page_end} "
                f"(Title: {s.title or 'N/A'}) ---\n{s.get_text()}"
                for s in sections
            ]
            try:
                with open(self.args.extracted_file, 'w', encoding='utf-8') as f:
                    f.write("\n\n\n".join(content))
                logging.getLogger("ppdf").info(
                    "Raw extracted text saved to: '%s'", self.args.extracted_file
                )
            except IOError as e:
                logging.getLogger("ppdf").error("Error saving raw text: %s", e)

    def _save_llm_output(self, markdown_text):
        """Saves the final LLM-generated markdown to a file."""
        if not self.args.output_file:
            return
        try:
            with open(self.args.output_file, 'w', encoding='utf-8') as f:
                f.write(markdown_text)
            logging.getLogger("ppdf").info(
                "\nLLM output saved to: '%s'", self.args.output_file
            )
        except IOError as e:
            logging.getLogger("ppdf").error("Error saving LLM output: %s", e)

    def _generate_output_with_llm(self, sections, system_prompt, run_stats):
        """Orchestrates chunking and processing sections with the LLM."""
        all_markdown, agg_stats = [], {'prompt_eval_count': 0, 'eval_count': 0, 'eval_duration': 0}
        chars_sent, chars_received = 0, 0
        chunks = Application._chunk_sections(sections, self.args.chunk_size)

        for i, chunk in enumerate(chunks):
            s_page, e_page = chunk[0].page_start, chunk[-1].page_end
            logging.getLogger("ppdf").info(
                "\nProcessing chunk %d/%d (Sections: %d, Pages: %s-%s)",
                i + 1, len(chunks), len(chunk), s_page, e_page
            )
            user_content = "\n\n".join(
                [f"# {s.title or 'Untitled'}\n\n{s.get_llm_text()}" for s in chunk]
            )
            full_response, chunk_stats = self._query_llm_api(
                system_prompt, user_content, self.tts_manager
            )
            if full_response:
                all_markdown.append(full_response)
                for key in agg_stats:
                    agg_stats[key] += chunk_stats.get(key, 0)
                chars_sent += len(system_prompt) + len(user_content)
                chars_received += len(full_response)
            else:
                all_markdown.append(f"\n[ERROR: Could not process chunk {i+1}]")

        run_stats.update({f'llm_{k}': v for k, v in agg_stats.items()})
        run_stats['llm_chars_sent'] = chars_sent
        run_stats['llm_chars_received'] = chars_received
        return "\n\n".join(all_markdown)

    def _build_system_prompt(self, base_prompt_text):
        """Prepares the final system prompt with conditional mandates."""
        system_prompt = base_prompt_text
        if self.args.translate:
            lang = self.args.translate.capitalize()
            system_prompt += (
                "\n\n**Translation Mandate:** After all formatting, you MUST "
                f"translate the entire Markdown output into {lang}."
            )
        return system_prompt

    @staticmethod
    def _chunk_sections(sections, size=4000):
        """Greedily chunks sections to maximize context window usage."""
        if not sections:
            return []
        chunks, current_chunk, current_len, i = [], [], 0, 0
        while i < len(sections):
            s = sections[i]
            s_len = len(f"# {s.title}\n") + len(s.get_llm_text())
            if s_len > size and not current_chunk:
                log_llm.warning(
                    "Section '%s' is larger than chunk size and will be "
                    "processed alone.", s.title
                )
                chunks.append([s])
                i += 1
                continue
            if current_chunk and (current_len + s_len) > size:
                chunks.append(current_chunk)
                current_chunk, current_len = [], 0
            current_chunk.append(s)
            current_len += s_len
            i += 1
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    def _query_llm_api(self, system, user, tts_manager=None):
        """Queries the Ollama /api/generate endpoint and streams response."""
        data = { "model": self.args.model, "system": system, "prompt": f"\n\n--- BEGIN DOCUMENT ---\n\n{user}\n\n--- END DOCUMENT ---", "stream": True }
        full_content, stats = "", {}
        try:
            r = requests.post(f"{self.args.url}/api/generate", json=data, stream=True)
            r.raise_for_status()

            if self.args.rich_stream:
                console = Console()
                live = Live(console=console, auto_refresh=False, vertical_overflow="visible")
                with live:
                    for line in r.iter_lines():
                        j, chunk = self._process_stream_line(line, tts_manager)
                        if chunk is not None:
                            full_content += chunk
                            live.update(Markdown(full_content), refresh=True)
                        if j and j.get('done'):
                            stats = j
            else:
                print()  # Add a newline before the stream
                for line in r.iter_lines():
                    j, chunk = self._process_stream_line(line, tts_manager)
                    if chunk is not None:
                        full_content += chunk
                        print(chunk, end='', flush=True)
                    if j and j.get('done'): stats = j
                print() # Add a newline after the stream

            return full_content.strip(), stats
        except requests.exceptions.RequestException as e:
            log_llm.error("Ollama API request failed: %s", e)
            return None, {}

    def _process_stream_line(self, line, tts_manager):
        """Helper to process a single line from the Ollama stream."""
        if not line:
            return None, None
        try:
            j = json.loads(line.decode('utf-8'))
            chunk = j.get('response', '')
            if chunk and tts_manager:
                tts_manager.add_text(chunk)
            return j, chunk
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, None

    @staticmethod
    def parse_arguments():
        """Parses command-line arguments for the script."""
        p = argparse.ArgumentParser(
            description="An advanced PDF text and structure extraction tool.",
            formatter_class=argparse.RawTextHelpFormatter,
            add_help=False,
            epilog="""Examples:
      python ppdf.py document.pdf -o "output.md"
      python ppdf.py document.pdf -S en
      python ppdf.py document.pdf -d llm,struct --color-logs
            """
        )
        S = Application.DEFAULT_FILENAME_SENTINEL
        g_opts = p.add_argument_group('Main Options')
        g_opts.add_argument("pdf_file", help="Path to the input PDF file.")
        g_opts.add_argument("-h", "--help", action="help", help="Show help.")

        g_proc = p.add_argument_group('Processing Control')
        g_proc.add_argument("-p", "--pages", default="all", metavar="P", help="Pages (e.g., '1,3,5-7').")
        g_proc.add_argument("-C", "--columns", default="auto", metavar="N", help="Force columns ('auto', 1-6).")
        g_proc.add_argument("--no-remove-footers", action="store_false", dest="remove_footers")
        g_proc.add_argument("-K", "--keep-style", action="store_true", help="Preserve bold/italic.")

        g_llm = p.add_argument_group('LLM Configuration')
        g_llm.add_argument("-M", "--model", default="llama3.1:latest", help="Ollama model.")
        g_llm.add_argument("-U", "--url", default="http://localhost:11434", help="Ollama API URL.")
        # FIX: Provide the correct integer default directly to argparse.
        g_llm.add_argument("-z", "--chunk-size", type=int, default=Application.DEFAULT_CHUNK_SIZE, help="Max chars per LLM chunk.")
        g_llm.add_argument("-t", "--translate", metavar="LANG", help="Translate output to language.")

        preset_group = g_llm.add_mutually_exclusive_group()
        preset_group.add_argument("--prompt-preset", default='strict', choices=PROMPT_PRESETS.keys())
        preset_group.add_argument("--batch-presets", action="store_true", help="Run for all presets.")

        g_out = p.add_argument_group('Script Output & Actions')
        g_out.add_argument("-o", "--output-file", nargs='?', const=S, default=None, metavar="F")
        g_out.add_argument("-e", "--extracted-file", nargs='?', const=S, default=None, metavar="F")
        g_out.add_argument("--rich-stream", action="store_true", help="Render live Markdown.")
        g_out.add_argument("--color-logs", action="store_true", help="Enable colored logging.")
        g_out.add_argument("-S", "--speak", nargs='?', const='en', choices=['en','es','ca'], help="Stream to speech.")
        g_out.add_argument("-D", "--dry-run", action="store_true", help="Analyze without LLM.")
        g_out.add_argument("-v", "--verbose", action="store_true", help="Enable INFO logging.")
        g_out.add_argument("-d", "--debug", nargs='?', const="all", dest="debug_topics", metavar="T")

        # FIX: The check for args.chunk_size is no longer needed and should be removed.
        return p.parse_args()

def main():
    """Main entry point for the script."""
    # This setup ensures a `core` package can be found
    core_dir = os.path.join(os.path.dirname(__file__), "core")
    os.makedirs(core_dir, exist_ok=True)
    init_path = os.path.join(core_dir, "__init__.py")
    if not os.path.exists(init_path):
        with open(init_path, "w") as f:
            pass

    # Basic logging config for early errors before full setup
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    try:
        args = Application.parse_arguments()
        app = Application(args)
        app.run()
    except FileNotFoundError as e:
        logging.getLogger("ppdf").critical(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logging.getLogger("ppdf").info("\nProcess interrupted by user. Exiting.")
        sys.exit(0)
    except Exception as e:
        logging.getLogger("ppdf").critical(
            "\nAn unexpected error occurred: %s", e, exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
