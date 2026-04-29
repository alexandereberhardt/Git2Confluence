from datetime import date
import anthropic
from passten.templates import Section
from passten.publisher import AUTO_GENERATED_MARKER


class Synthesizer:
    def __init__(self, api_key: str, model: str = 'claude-sonnet-4-6-20250514'):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def _build_prompt(self, section: Section, extracted_data: dict) -> str:
        repos_context = []
        for repo in extracted_data.get('repos', []):
            repo_block = f"\n### Repository: {repo['project']}\n"
            for key, value in repo.items():
                if key in ('project', 'project_id', 'branch'):
                    continue
                if isinstance(value, str):
                    repo_block += f"\n**{key}:**\n```\n{value[:3000]}\n```\n"
                elif isinstance(value, dict):
                    for fname, content in list(value.items())[:5]:
                        repo_block += f"\n**{fname}:**\n```\n{content[:2000]}\n```\n"
                elif isinstance(value, list):
                    repo_block += f"\n**{key}:** {', '.join(str(v) for v in value[:20])}\n"
            repos_context.append(repo_block)

        questions = '\n'.join(f"- {q}" for q in section.guiding_questions)

        return f"""You are generating documentation for a Porsche PASS Template (PASSTEN) Confluence page.

## Section: {section.title}

## Guiding Questions to Address:
{questions}

## Extracted Data from GitLab Repositories:
{''.join(repos_context)}

## Instructions:
- Write in English
- Output valid Confluence Storage Format (HTML)
- Be factual and concise — only state what is evidenced by the extracted data
- Structure with <h2> subsections as appropriate
- Include a table of components/services where relevant
- Do NOT include the page title as <h1> — Confluence adds it automatically
- Do NOT wrap output in code blocks — return raw HTML only
- Reference specific repositories by name
- If data is insufficient for a complete answer, note what is missing
"""

    def synthesize_section(self, section: Section, extracted_data: dict) -> str:
        prompt = self._build_prompt(section, extracted_data)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{'role': 'user', 'content': prompt}],
        )
        html_content = response.content[0].text
        header = (f'{AUTO_GENERATED_MARKER}\n'
                  f'<ac:structured-macro ac:name="info" ac:schema-version="1">'
                  f'<ac:rich-text-body><p>Auto-generated from GitLab repositories. '
                  f'Last updated: {date.today().isoformat()}. '
                  f'Do not edit sections marked as auto-generated.</p>'
                  f'</ac:rich-text-body></ac:structured-macro>\n')
        return header + html_content

    def generate_placeholder(self, section: Section) -> str:
        questions_html = ''.join(f'<li>{q}</li>' for q in section.guiding_questions)
        return (f'<ac:structured-macro ac:name="note" ac:schema-version="1">'
                f'<ac:rich-text-body><p>This section requires manual input. '
                f'Please address the following guiding questions:</p>'
                f'<ul>{questions_html}</ul>'
                f'</ac:rich-text-body></ac:structured-macro>')
