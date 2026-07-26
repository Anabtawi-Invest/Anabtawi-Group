# AI Recruitment Scoring — Odoo 19

## Overview

AI-Powered CV Analysis, Smart Scoring & Interview Question Generation for Odoo 19 Recruitment.

## Features

- **Multi-Dimensional AI Scoring** — Skills (🔧), Experience (📊), Education (🎓) & Cultural Fit (🤝)
- **AI-Generated Summaries** — Instant candidate profile insights from uploaded CVs
- **Smart Interview Questions** — Categorized (Technical, Behavioral, Role-Specific, Situational) with difficulty levels
- **Bulk AI Scoring** — Process multiple applicants at once via tree view action
- **Skill Gap Analysis** — Matched, missing, and extra skills identification
- **Dual AI Provider Support** — Google Gemini & OpenAI
- **PDF & DOCX Support** — Automatic text extraction from both resume formats
- **Configurable per Job Position** — Required/preferred skills, experience years, education level, custom criteria, and scoring weights

## Installation

### Prerequisites

Install the required Python packages in your Odoo server environment:

```bash
# For PDF parsing
pip install pymupdf

# For DOCX parsing
pip install python-docx

# For Google Gemini AI provider
pip install google-generativeai

# For OpenAI provider (if using OpenAI)
pip install openai
```

### Module Installation

1. Copy the `ai_recruitment_scoring` folder to your Odoo addons path
2. Restart the Odoo server
3. Go to **Apps** → Update Apps List
4. Search for "AI Recruitment Scoring" and install

## Configuration

1. Go to **Settings** → **AI Recruitment**
2. Select your **AI Provider** (Google Gemini or OpenAI)
3. Enter your **API Key**
4. Set the **AI Model** (default: `gemini-2.0-flash`)
5. Choose the **Response Language**
6. Save settings

## Usage

### Setting Up Job Positions

1. Open a Job Position form
2. Go to the **🤖 AI Scoring Criteria** tab
3. Fill in:
   - Required Skills (comma-separated)
   - Preferred Skills
   - Min. Experience (years)
   - Min. Education Level
   - Scoring Weights (skills, experience, education, cultural fit)
   - Custom Scoring Criteria (optional free text)
   - Interview Question Focus (optional)

### Analyzing a Single Applicant

1. Open an applicant record
2. Click **🤖 AI Analyze CV** in the header
3. The AI will:
   - Extract text from the attached PDF/DOCX
   - Score the candidate across 4 dimensions
   - Generate a rich HTML summary
   - Create categorized interview questions
4. Results appear in the **🤖 AI Analysis** tab

### Bulk Scoring

1. Go to **Recruitment** → **Applications** (tree view)
2. Select multiple applicants
3. Use **Action** → **Bulk AI Scoring**
4. Choose analysis mode and start

## Dependencies

- `hr_recruitment` (Odoo Recruitment)
- `hr` (Employees)
- `mail` (Discuss)
- `calendar` (Calendar)

## License

LGPL-3
