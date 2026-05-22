# Frontend Prompt: Support Question Answer CSV Imports

You are working on the frontend for this Django/DRF backend. Update the admin question import and question display UI to support imported answer CSVs.

## Backend Context

The backend supports bulk importing question/answer CSV files at:

```text
POST /api/accounts/admin/questions/bulk-import/
```

Use multipart form data:

```text
file=<csv file>
subject_id=<optional>
semester_id=<optional>
year=<optional>
answers_file=<optional separate answers csv>
```

The endpoint now supports CSVs shaped like:

```csv
question_id,semester,subject,year,group,question,answer
34605,Semester 1,Introduction to Information Technology,2081,Section A,"Question text","Markdown answer"
```

It also still supports the older/importer format:

```csv
question_text,answer_text,marks
```

And a separate answers CSV:

```csv
question_id,answer_markdown,image_paths,answer_source_url
```

## Updated Question Fields

Question API responses can include:

```json
{
  "id": 1,
  "source_question_id": "34605",
  "source_url": "",
  "answer_source_url": "",
  "answer_image_paths": "",
  "section": "Section A",
  "question_text": "Compare primary memory with secondary memory.",
  "answer_text": "**Markdown answer**",
  "marks": "",
  "order": 0,
  "year": "2081",
  "subject": "Introduction to Information Technology",
  "semester": "Semester 1"
}
```

## Frontend Tasks

1. Update the admin bulk question import UI.
   - Allow uploading `all_years_answers.csv` or `year_2081_answers.csv` directly as the main `file`.
   - Keep support for an optional separate `answers_file`.
   - Show a clear imported count and row-level errors returned by the API.
   - Mention supported headers in helper text: `question_id, semester, subject, year, group, question, answer`.

2. Update the admin questions table/detail UI.
   - Display `source_question_id`.
   - Display `section`.
   - Display `answer_source_url` as a link when present.
   - Display `answer_image_paths` when present.
   - Keep existing edit/delete behavior working.

3. Update the public question answer display.
   - Render `answer_text` as Markdown if the app already uses Markdown rendering.
   - Preserve tables, bold text, lists, and line breaks.
   - If no Markdown renderer exists, add a safe renderer such as `react-markdown` with `remark-gfm`.
   - Do not render raw HTML from answers unless sanitized.

4. Make imports idempotent from the UI perspective.
   - Re-uploading the same CSV should be treated as an update/sync, not as a duplicate import.
   - Use the backend response `imported_count` and `questions` array to refresh the visible list.

5. Add or update frontend validation.
   - Require a CSV file before submit.
   - Accept `.csv`.
   - Show loading, success, and error states.
   - Do not require `subject_id` or `year` when the CSV already contains `semester`, `subject`, and `year`.

## Example Request

```ts
const formData = new FormData();
formData.append("file", csvFile);

if (answersFile) {
  formData.append("answers_file", answersFile);
}

const response = await fetch("/api/accounts/admin/questions/bulk-import/", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${accessToken}`,
  },
  body: formData,
});

const data = await response.json();
```

Do not set `Content-Type` manually for multipart requests; let the browser set the boundary.

## Acceptance Criteria

- Admin can upload `year_2081_answers.csv` directly.
- Admin can upload `all_years_answers.csv` directly.
- Imported answers render with Markdown tables and formatting.
- Admin question list shows source id and section/group.
- Re-uploading the same CSV does not create duplicate questions.
- API row errors are visible to the admin.
