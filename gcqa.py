import json
import re
import requests
import argparse
import os
import logging
import sys
import time

# --- LOGGING CONFIGURATION ---
log_task = logging.getLogger("gcqa.task")
log_api = logging.getLogger("gcqa.ollama")
log_stats = logging.getLogger("gcqa.stats")

def setup_logging(verbose=False):
    """Configures multi-channel logging. Verbose mode allows viewing model output."""
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    for l in [log_task, log_api, log_stats]:
        l.handlers = []
        l.setLevel(level)
        l.addHandler(handler)
        l.propagate = False

class Application:
    """Main application logic for OSR dataset generation with readable debug logs."""

    def __init__(self, args):
        self.args = args
        self.stats = {"tokens": 0, "duration": 0.0}
        self.url = f"{args.url}/api/generate"

    def get_sections(self, filepath):
        """Extracts sections and flags technical tables using regex."""
        filename_root = os.path.splitext(os.path.basename(filepath))[0].upper()
        log_task.info(f"Analyzing file: {filepath} (Root: {filename_root})")

        table_regex = re.compile(r'\|\s*[-:]+\s*\|')

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            log_task.error(f"Read error: {e}")
            return []

        sections, stack, content = [], [filename_root], []
        has_table = False

        for line in lines:
            m = re.match(r'^(#{1,6})\s+(.*)', line)
            if m:
                if content and stack:
                    sections.append({
                        "anchor": " > ".join(stack),
                        "content": "".join(content).strip(),
                        "has_table": has_table
                    })
                level, text = len(m.group(1)), m.group(2).strip()
                stack = stack[:level] + [f"H{level}: {text}"]
                content, has_table = [], False
            else:
                content.append(line)
                if table_regex.search(line):
                    has_table = True

        if content:
            sections.append({
                "anchor": " > ".join(stack),
                "content": "".join(content).strip(),
                "has_table": has_table
            })

        log_task.info(f"Identified {len(sections)} sections.")
        return sections

    def find_qa_pairs(self, data):
        """Recursively extracts Q&A pairs from the LLM JSON response."""
        if isinstance(data, list):
            return [i for i in data if isinstance(i, dict) and 'q' in i and 'a' in i]
        if isinstance(data, dict):
            if 'q' in data and 'a' in data: return [data]
            for v in data.values():
                found = self.find_qa_pairs(v)
                if found: return found
        return []

    def query_ollama(self, prompt_type, sec_data):
        """Queries Ollama and logs the generated response in raw or pretty format."""
        anchor, content, has_table = sec_data['anchor'], sec_data['content'], sec_data['has_table']
        num_q = "7 i 10" if has_table or len(content) > 1500 else "3 i 6"

        if prompt_type == "summary":
            table_instr = "\nIMPORTANT: Si el text conté taules de Markdown, MANTÍN-LES ÍNTEGRES dins del resum." if has_table else ""
            prompt = (f"Ets un expert en jocs de rol OSR. Fes un resum concís i professional "
                      f"en CATALÀ d'aquesta secció: {anchor}{table_instr}\n\nTEXT:\n{content}\n\n"
                      f"Respon només amb el resum (i les taules si n'hi ha).")
            fmt = ""
        else:
            table_instr = (" AQUESTA SECCIÓ CONTÉ TAULES TÈCNIQUES. Genera preguntes que obliguin "
                           "a extreure dades numèriques de les files.") if has_table else ""
            prompt = (f"Expert OSR.{table_instr} Genera entre {num_q} parells de Pregunta i Resposta "
                      f"en CATALÀ. POSICIÓ: {anchor}\nTEXT: {content}\n"
                      f"Respon exclusivament en format JSON: [{{'q':'...', 'a':'...'}}]")
            fmt = "json"

        payload = {
            "model": self.args.model,
            "prompt": prompt,
            "stream": False,
            "format": fmt,
            "options": {
                "num_ctx": 16384,
                "num_predict": 2048,
                "temperature": 0.2
            }
        }

        try:
            start_time = time.monotonic()
            log_api.debug(f"Requesting {prompt_type.upper()} for: {anchor}")

            r = requests.post(self.url, json=payload, timeout=300)
            r.raise_for_status()
            resp_obj = r.json()
            raw_text = resp_obj.get('response', '')

            # --- PRETTY LOGGING LOGIC ---
            if prompt_type == "summary":
                log_api.debug(f"MODEL SUMMARY RESPONSE:\n{raw_text}")
            else:
                try:
                    # Parse the JSON string from the model and re-dump it with indentation
                    pretty_json = json.dumps(json.loads(raw_text), indent=2, ensure_ascii=False)
                    log_api.debug(f"MODEL QA RESPONSE (PRETTY):\n{pretty_json}")
                except Exception:
                    # Fallback to raw text if parsing fails
                    log_api.debug(f"MODEL QA RESPONSE (RAW - PARSE FAILED):\n{raw_text}")

            dur = time.monotonic() - start_time
            self.stats["tokens"] += resp_obj.get('eval_count', 0)
            self.stats["duration"] += dur

            if prompt_type == "summary":
                return raw_text.strip()

            return self.find_qa_pairs(json.loads(raw_text))
        except Exception as e:
            log_task.error(f"Error at {anchor} ({prompt_type}): {e}")
            return [] if prompt_type == "qa" else None

    def run(self):
        """Main loop with state persistence and speed tracking."""
        base = os.path.splitext(os.path.basename(self.args.input))[0]
        out_path = os.path.join(self.args.output_dir, f"{base}.json")
        state_path = os.path.join(self.args.output_dir, f"{base}.state")

        if not os.path.exists(self.args.output_dir):
            os.makedirs(self.args.output_dir)

        last_idx = -1
        if os.path.exists(state_path):
            with open(state_path, 'r') as f:
                last_idx = int(f.read().strip())
            log_task.info(f"Resuming from section {last_idx + 1}")

        sections = self.get_sections(self.args.input)

        with open(out_path, 'a', encoding='utf-8') as f_out:
            for i, sec in enumerate(sections):
                if i <= last_idx or len(sec['content']) < 40:
                    continue

                log_task.info(f"[{i+1}/{len(sections)}] Processing: {sec['anchor']} {'(TABLE)' if sec['has_table'] else ''}")

                # 1. Summary Phase
                summary = self.query_ollama("summary", sec)
                if summary:
                    sum_entry = {
                        "messages": [
                            {"role": "user", "content": f"REF: {sec['anchor']}\n\nQ: Que diu aquest apartat del document?"},
                            {"role": "assistant", "content": summary}
                        ]
                    }
                    f_out.write(json.dumps(sum_entry, ensure_ascii=False) + "\n")

                # 2. Detailed Q&A Phase
                pairs = self.query_ollama("qa", sec)
                for p in pairs:
                    qa_entry = {
                        "messages": [
                            {"role": "user", "content": f"REF: {sec['anchor']}\n\nQ: {p['q']}"},
                            {"role": "assistant", "content": p['a']}
                        ]
                    }
                    f_out.write(json.dumps(qa_entry, ensure_ascii=False) + "\n")

                f_out.flush()
                with open(state_path, 'w') as fs:
                    fs.write(str(i))

                tps = self.stats["tokens"]/self.stats["duration"] if self.stats["duration"] > 0 else 0
                log_task.info(f"  -> OK. Speed: {tps:.1f} tps")

        if self.stats["duration"] > 0:
            avg_tps = self.stats["tokens"]/self.stats["duration"]
            log_stats.info(f"Generation complete. Average: {avg_tps:.1f} tokens/s")

        if os.path.exists(state_path):
            os.remove(state_path)

def main():
    parser = argparse.ArgumentParser(description="Catalan CQA Dataset Generator with Pretty Logging.")
    parser.add_argument("input", help="Source Markdown file path")
    parser.add_argument("-o", "--output-dir", default=".", help="Output directory")
    parser.add_argument("-m", "--model", default="gemma3:27b", help="Ollama model name")
    parser.add_argument("-u", "--url", default="http://localhost:11434", help="Ollama API URL")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logs with pretty responses")

    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        Application(args).run()
    except KeyboardInterrupt:
        log_task.info("\nInterrupted by user. State saved.")
        sys.exit(0)

if __name__ == "__main__":
    main()
