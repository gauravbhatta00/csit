# Frontend Implementation Prompt

Use this prompt to update both frontend clients after the latest Ramro CSIT API merge.

## Repositories

- Next.js web frontend: `../noteshare`
- React Native / Expo frontend: `../ramro-csit`
- Backend source of truth: current repo, especially `academics/serializers.py`, `academics/views.py`, `accounts/urls.py`, and `accounts/views.py`

## Backend Changes To Support

The backend now has these frontend-visible changes:

- Public notes and year questions are paginated with Django REST Framework page-number pagination.
- Public note list supports `?unit=<unit_slug>` filtering.
- Note responses include richer unit metadata and credit metadata.
- Public question answers are gated: unauthenticated users receive questions, but `answer_text`, `answer_source_url`, `answer_image_paths`, and `approved_contributions` may be empty.
- Media URL fields are safer now and may be `null` or `""` instead of throwing or returning broken paths.
- New reusable credit-person model/API exists for admin use: `GET/POST /accounts/admin/credit-people/`.
- Admin note create/edit still primarily uses legacy credit fields in the current backend: `credit_name`, `credit_designation`, `credit_url`, and `credit_image`. Do not assume `credit_person` is accepted by admin note create/edit unless you verify and update the backend too.

## API Contract

Paginated endpoints return this shape:

```ts
type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
```

These endpoints must accept both old array responses and new paginated responses where practical:

```text
GET /subjects/:subjectSlug/notes/?unit=:unitSlug&page=:page&page_size=:pageSize
GET /subjects/:subjectSlug/questions/:year/?page=:page&page_size=:pageSize
```

Public `Note` fields:

```ts
type NoteCreditPerson = {
  id?: number | null;
  name: string;
  designation: string;
  link_url: string;
  image: string | null;
  image_url: string;
  portfolio_url: string;
};

type Note = {
  id: number;
  title: string;
  slug: string;
  body: string;
  pdf_file: string | null;
  unit: number | null;
  unit_slug: string;
  unit_title: string;
  unit_order: number | null;
  unit_duration: string;
  unit_content: string;
  credit_person: NoteCreditPerson | null;
  credit: NoteCreditPerson | null;
  credit_name: string;
  credit_designation: string;
  credit_url: string;
  credit_image: string | null;
  order: number;
  updated_at: string;
};
```

Public `Question` fields:

```ts
type Question = {
  id: number;
  section: {
    id: number;
    title: string;
    instruction: string;
    order: number;
  } | null;
  source_question_id?: string;
  source_url?: string;
  answer_source_url: string;
  answer_image_paths: string;
  question_text: string;
  answer_text: string;
  marks: string;
  order: number;
  approved_contributions: Array<{
    id: number;
    username: string;
    answer_text: string;
    image: string | null;
    created_at: string;
  }>;
};
```

Admin credit-person endpoint:

```text
GET  /accounts/admin/credit-people/?search=<name>
POST /accounts/admin/credit-people/
```

Credit-person create payload supports JSON or multipart fields:

```ts
{
  name: string;
  designation?: string;
  link_url?: string;
  image?: File; // web multipart only
  image_url?: string;
  portfolio_url?: string;
}
```

## Next.js Web Tasks: `../noteshare`

1. Update or verify shared API response handling in `src/api/academics.api.ts`.
   - Keep a helper like `readListResponse<T>()`.
   - `fetchSubjectNotes()` and `fetchSubjectQuestions()` must handle both `T[]` and `PaginatedResponse<T>`.
   - Add optional `page` and `page_size` params if the UI needs load-more/infinite pagination.

2. Update or verify public academic types in `src/interfaces/academics.interface.ts`.
   - Ensure `Note`, `NoteCreditPerson`, `Question`, `QuestionSection`, and `AnswerContribution` match the backend fields above.
   - Treat all media fields as nullable or empty strings.

3. Update the subject notes UI in `src/components/Semester/SubjectPage.tsx`.
   - Use `unit_title`, `unit_order`, `unit_duration`, and `unit_content` for chapter navigation and note context.
   - Read credit display from `note.credit ?? note.credit_person`, falling back to legacy fields only when needed.
   - Do not render broken image/PDF links when media fields are `null` or `""`.
   - If only the first page of notes/questions is currently shown, either request a larger `page_size` within backend limits or implement load-more/infinite paging.

4. Update or verify admin credit support in `src/api/admin.api.ts`, `src/interfaces/admin.interface.ts`, and `src/components/Admin/AdminSubjectResourcesPage.tsx`.
   - `fetchAdminCreditPeople()` and `createAdminCreditPerson()` should call `/accounts/admin/credit-people/`.
   - If the admin form lets users pick a reusable credit person, verify the backend accepts `credit_person` on note create/edit before sending it. If it does not, either keep the selector as a helper that fills legacy fields or update the backend first.
   - Current admin note create/edit payloads should include `unit`, `pdf_file`, `credit_name`, `credit_designation`, `credit_url`, and `credit_image`.

5. Verify question answer behavior.
   - Guests should see question text but not answers.
   - Authenticated users should see `answer_text`, `answer_source_url`, `answer_image_paths`, and approved contributions when available.
   - Avoid UI states that look broken when answer fields are intentionally empty for guests.

6. Run:

```bash
cd ../noteshare
npm run lint
npm run build
```

## React Native / Expo Tasks: `../ramro-csit`

Use existing project patterns: Expo Router, React Query/Zustand where already used, `expo-image` for images, `FlashList` for large lists, and `StyleSheet.create` or the existing themed style helpers.

1. Update or verify API handling in `services/api.ts`.
   - `fetchSubjectNotes()` and `fetchSubjectQuestions()` must handle both arrays and paginated responses.
   - Preserve authenticated fetching for questions so answers are included for logged-in users.
   - If syncing only receives one page, request a safe `page_size` or loop through `next` pages.

2. Update or verify contract types in `services/types.ts`.
   - Match the `Note`, `NoteCreditPerson`, `Question`, and `AnswerContribution` shapes above.
   - Media fields must allow `null` or `""`.

3. Update offline sync in `db/sync.ts`, `db/schema.ts`, `db/rows.ts`, and `db/queries.ts` as needed.
   - Persist unit fields: `unit`, `unit_slug`, `unit_title`, `unit_order`, and optionally `unit_content` if the mobile UI should show chapter outline.
   - Persist credit data as JSON from `note.credit ?? note.credit_person`, with fallback to legacy credit fields if present.
   - If schema columns are added, add a migration-safe path for existing installed apps.
   - Do not wipe user progress, bookmarks, offline-note registry, recent notes, or downloaded PDFs.

4. Update note list/detail UI.
   - Relevant files include `components/feature/NoteCard.tsx`, `components/feature/NoteRow.tsx`, `components/feature/sections/NotesSection.tsx`, `components/feature/sections/SyllabusSection.tsx`, and `app/viewer/note/[id].tsx`.
   - Show chapter number/title/duration using the new unit fields.
   - Show credit attribution when available.
   - Resolve PDFs/images with the existing media URL helper and handle missing files gracefully.
   - Use `FlashList` for large note/question lists and keep item render callbacks stable.
   - Use `expo-image` for remote credit images.

5. Update question answer UI.
   - Guests should be told to sign in when answers are empty because of auth gating.
   - Authenticated users should see answers and approved answer contributions.
   - Do not treat empty answer fields as a failed API call.

6. Run:

```bash
cd ../ramro-csit
npx tsc --noEmit
npm run start
```

If the project has no TypeScript script, use the direct `npx tsc --noEmit` command.

## Acceptance Checklist

- Web and mobile both compile.
- Notes load for a subject when the backend returns either an array or `{ results: [...] }`.
- Question lists load for a year when the backend returns either an array or `{ results: [...] }`.
- Unit-specific note URLs/tabs still work with `?unit=<unit_slug>`.
- PDFs and images never render as broken links when backend returns `null` or `""`.
- Note credit displays correctly for both reusable `credit` objects and legacy credit fields.
- Admin can list/create credit people.
- Admin note create/edit remains compatible with the current backend payload.
- Guest users can browse questions without answers; logged-in users can view answers.
