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
log_api = logging.getLogger("gcqa.backend")
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

# --- PROVIDER CLASSES (BACKENDS) ---

class GeminiBackend:
    """Handles communication with the Google Gemini API using the new GenAI SDK."""
    def __init__(self, args):
        try:
            from google import genai
            from google.genai import types

            self.client = genai.Client(api_key=args.api_key)
            self.types = types

            log_task.info("Fetching available Gemini models...")
            available_models = self.list_available_models()

            # The API often returns "models/gemini-2.0-flash", but users might input
            # "gemini-2.0-flash". We check both the full name and the short name.
            requested_model = args.model
            valid_names = []
            for m in available_models:
                valid_names.append(m.name)
                valid_names.append(m.name.split('/')[-1]) # Add "gemini-2.0-flash" short form

            if requested_model not in valid_names:
                log_task.error(f"Error: Model '{requested_model}' not found in your account.")
                log_task.info("Available models for this API key:")
                for name in sorted(set(valid_names)):
                    if name.startswith("models/"): # Only print the full resource name for clarity
                        log_task.info(f" - {name}")
                sys.exit(1)

            self.model_id = requested_model
            log_task.info(f"Initialized Gemini Backend with model: {self.model_id}")

        except ImportError:
            log_task.error("Error: 'google-genai' is not installed. Run: pip install google-genai")
            sys.exit(1)

    def generate(self, prompt, is_json_format=False):
        config = {
            "temperature": 0.2,
            "max_output_tokens": 2048,
        }

        # Use Controlled Generation (JSON Mode) if requested
        if is_json_format:
            config["response_mime_type"] = "application/json"

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=config
            )
            # Gemini response object includes usage metadata
            tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            return response.text, tokens
        except Exception as e:
            log_api.error(f"Gemini API Error: {e}")
            return "", 0

    def list_available_models(self):
        """Fetches and returns all models available to the current API key."""
        try:
            # Returns an iterator of models
            models = list(self.client.models.list())
            for m in models:
                actions = ", ".join(m.supported_actions)
                log_api.debug(f"Model Found: {m.name} | Actions: {actions}")
            return models
        except Exception as e:
            log_api.error(f"Could not list models: {e}")
            return []

class OllamaBackend:
    """Handles communication with the Ollama API."""
    def __init__(self, args):
        self.url = f"{args.url}/api/generate"
        self.model = args.model

    def generate(self, prompt, is_json_format=False):
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json" if is_json_format else "",
            "options": {
                "num_ctx": 16384,
                "num_predict": 2048,
                "temperature": 0.2
            }
        }
        try:
            r = requests.post(self.url, json=payload, timeout=300)
            r.raise_for_status()
            resp_obj = r.json()
            return resp_obj.get('response', ''), resp_obj.get('eval_count', 0)
        except Exception as e:
            log_api.error(f"Ollama API Error: {e}")
            return "", 0

class MLXBackend:
    """
    MLX Backend with fixes for:
    1. Sampler arguments (fixes 'unexpected keyword argument temp').
    2. Markdown stripping (fixes JSON parsing errors).
    """
    def __init__(self, args):
        try:
            from mlx_lm import load
            log_task.info(f"Loading MLX model: {args.model}...")
            self.model, self.tokenizer = load(args.model)
        except ImportError:
            log_task.error("Error: 'mlx-lm' is not installed. Please run 'pip install mlx-lm'")
            sys.exit(1)

    def generate(self, prompt, is_json_format=False):
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler

        # 1. Chat Template (Crucial for Gemma 3)
        messages = [{"role": "user", "content": prompt}]

        # Apply chat template if available in the tokenizer
        if hasattr(self.tokenizer, "apply_chat_template"):
            formatted_prompt = self.tokenizer.apply_chat_template(messages, add_generation_prompt=True)
        else:
            formatted_prompt = prompt

        # 2. Fix: Explicit Sampler creation to avoid API errors
        sampler = make_sampler(temp=0.2)

        # 3. Generate
        response = generate(
            self.model,
            self.tokenizer,
            prompt=formatted_prompt,
            sampler=sampler,
            max_tokens=2048,
            verbose=False
        )

        # 4. Fix: Clean Markdown for JSON consistency with Ollama
        if is_json_format:
            # Extract content between [ and ] to remove ```json wrapper
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if match:
                response = match.group(0)

        # Estimate tokens
        token_count = len(self.tokenizer.encode(response))
        return response, token_count

# --- APPLICATION LOGIC ---

class Application:
    """Main application logic for OSR dataset generation with readable debug logs."""

    def __init__(self, args):
        self.args = args
        self.stats = {"tokens": 0, "duration": 0.0}

        # Initialize the appropriate backend based on arguments
        if args.provider == "mlx":
            self.backend = MLXBackend(args)
        elif args.provider == "gemini":
            self.backend = GeminiBackend(args)
        else:
            self.backend = OllamaBackend(args)

    def get_sections(self, filepath):
        """Parses the Markdown file to extract sections, preserving hierarchy and detecting tables."""
        filename_root = os.path.splitext(os.path.basename(filepath))[0].upper()
        log_task.info(f"Analyzing file: {filepath} (Root: {filename_root})")

        # Regex to detect Markdown tables
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
            # Match Markdown headers (#, ##, etc.)
            m = re.match(r'^(#{1,6})\s+(.*)', line)
            if m:
                # Save previous section if it exists
                if content and stack:
                    sections.append({
                        "anchor": " > ".join(stack),
                        "content": "".join(content).strip(),
                        "has_table": has_table
                    })
                # Update hierarchy stack
                level, text = len(m.group(1)), m.group(2).strip()
                stack = stack[:level] + [f"H{level}: {text}"]
                content, has_table = [], False
            else:
                content.append(line)
                if table_regex.search(line):
                    has_table = True

        # Append the final section
        if content:
            sections.append({
                "anchor": " > ".join(stack),
                "content": "".join(content).strip(),
                "has_table": has_table
            })

        log_task.info(f"Identified {len(sections)} sections.")
        return sections

    def find_qa_pairs(self, data):
        """Recursively searches for Q&A pairs (keys 'q' and 'a') in a JSON object/list."""
        if isinstance(data, list):
            return [i for i in data if isinstance(i, dict) and 'q' in i and 'a' in i]
        if isinstance(data, dict):
            if 'q' in data and 'a' in data: return [data]
            for v in data.values():
                found = self.find_qa_pairs(v)
                if found: return found
        return []

    def process_section(self, prompt_type, sec_data):
        """Constructs the prompt, queries the backend, and handles logging."""
        anchor, content, has_table = sec_data['anchor'], sec_data['content'], sec_data['has_table']

        # Adjust question count based on content density or presence of tables
        num_q = "7 i 10" if has_table or len(content) > 1500 else "3 i 6"

        is_json = False

        # --- PROMPT CONSTRUCTION (CATALAN) ---
        if prompt_type == "summary":
            table_instr = "\nIMPORTANT: Si el text conté taules de Markdown, MANTÍN-LES ÍNTEGRES dins del resum." if has_table else ""
            prompt = (f"Ets un expert en jocs de rol de la 'Vella Escola' (OSR). "
                      f"Fes un resum tècnic i precís en CATALÀ de la secció: {anchor}. "
                      f"{table_instr}\n\n"
                      f"TEXT A RESUMIR:\n{content}\n\n"
                      f"Respon només amb el resum, mantenint el to del manual original.")
        else:
            table_instr = (" AQUESTA SECCIÓ CONTÉ TAULES TÈCNIQUES. Genera preguntes que obliguin "
                           "a extreure dades numèriques de les files.") if has_table else ""
            prompt = (f"Ets un expert en jocs de rol de la 'Vella Escola' (OSR). {table_instr} "
                      f"Genera entre {num_q} parells de Pregunta i Resposta en CATALÀ "
                      f"basant-te en la secció: {anchor}.\n"
                      f"TEXT:\n{content}\n"
                      f"LES PREGUNTES han de ser directes. LES RESPOSTES han de ser informatives.\n"
                      f"Respon exclusivament en format JSON: [{{\"q\": \"...\", \"a\": \"...\"}}]")
            is_json = True
        # -------------------------------------

        try:
            start_time = time.monotonic()
            log_api.debug(f"Requesting {prompt_type.upper()} for: {anchor}")

            # Backend Call
            response_text, tokens = self.backend.generate(prompt, is_json_format=is_json)

            # Stats & Logging
            self.stats["tokens"] += tokens
            self.stats["duration"] += (time.monotonic() - start_time)

            if prompt_type == "summary":
                log_api.debug(f"SUMMARY:\n{response_text}")
                return response_text.strip()
            else:
                try:
                    pretty_json = json.dumps(json.loads(response_text), indent=2, ensure_ascii=False)
                    log_api.debug(f"MODEL QA RESPONSE (PRETTY):\n{pretty_json}")
                except Exception:
                    log_api.debug(f"MODEL QA RESPONSE (RAW - PARSE FAILED):\n{response_text}")

            # JSON parsing (Backend has already cleaned the markdown!)
            data = json.loads(response_text)
            pairs = self.find_qa_pairs(data)
            log_api.debug(f"Extracted {len(pairs)} QA pairs.")
            return pairs

        except Exception as e:
            log_task.error(f"Error processing {anchor} ({prompt_type}): {e}")
            return [] if prompt_type == "qa" else None

    def run(self):
        """Main execution loop."""
        base = os.path.splitext(os.path.basename(self.args.input))[0]
        out_path = os.path.join(self.args.output_dir, f"{base}.json")
        state_path = os.path.join(self.args.output_dir, f"{base}.state")

        if not os.path.exists(self.args.output_dir):
            os.makedirs(self.args.output_dir)

        # Resume from state file if it exists
        last_idx = -1
        if os.path.exists(state_path):
            with open(state_path, 'r') as f:
                last_idx = int(f.read().strip())
            log_task.info(f"Resuming from section index {last_idx + 1}")

        sections = self.get_sections(self.args.input)

        with open(out_path, 'a', encoding='utf-8') as f_out:
            for i, sec in enumerate(sections):
                # Skip already processed sections or very short ones
                if i <= last_idx or len(sec['content']) < 40:
                    continue

                log_task.info(f"[{i+1}/{len(sections)}] Processing: {sec['anchor']} {'(TABLE)' if sec['has_table'] else ''}")

                # 1. Summary Generation Phase
                summary = self.process_section("summary", sec)
                if summary:
                    sum_entry = {
                        "messages": [
                            {"role": "user", "content": f"REF: {sec['anchor']}\n\nQ: Que diu aquest apartat del document?"},
                            {"role": "assistant", "content": summary}
                        ]
                    }
                    f_out.write(json.dumps(sum_entry, ensure_ascii=False) + "\n")

                # 2. Detailed Q&A Phase
                pairs = self.process_section("qa", sec)
                for p in pairs:
                    entry = {
                        "messages": [
                            {"role": "user", "content": f"REF: {sec['anchor']}\n\nQ: {p['q']}"},
                            {"role": "assistant", "content": p['a']}
                        ]
                    }
                    f_out.write(json.dumps(entry, ensure_ascii=False) + "\n")

                # Flush to disk and save state
                f_out.flush()
                with open(state_path, 'w') as fs: fs.write(str(i))

                # Speed logging
                tps = self.stats["tokens"]/self.stats["duration"] if self.stats["duration"] > 0 else 0
                log_task.info(f"  -> OK. Speed: {tps:.1f} tps")

        # Final statistics
        if self.stats["duration"] > 0:
            avg_tps = self.stats["tokens"]/self.stats["duration"]
            log_stats.info(f"Generation complete. Average: {avg_tps:.1f} tokens/s")

        # Cleanup state file
        if os.path.exists(state_path):
            os.remove(state_path)

def main():
    parser = argparse.ArgumentParser(description="Catalan CQA Dataset Generator.")
    parser.add_argument("input", help="Source Markdown file path")
    parser.add_argument("-o", "--output-dir", default=".", help="Output directory")
    parser.add_argument("-p", "--provider", choices=["ollama", "mlx", "gemini"], default="ollama", help="Inference provider to use")
    parser.add_argument("-k", "--api-key", default=os.environ.get("GAIS_APIKEY"), help="Gemini API Key (Google AI Studio)")
    parser.add_argument("-u", "--url", default="http://localhost:11434", help="Ollama API URL (ignored if using MLX)")
    parser.add_argument("-m", "--model", default="gemma3:27b", help="Ollama model name or MLX HuggingFace path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logs with model outputs")

    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        Application(args).run()
    except KeyboardInterrupt:
        log_task.info("\nInterrupted by user. State saved.")
        sys.exit(0)

if __name__ == "__main__":
    main()
