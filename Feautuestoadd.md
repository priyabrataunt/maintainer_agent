1. Finish multi-file analysis
   Make the analyzer inspect every file in the files list.
2. Remove duplicated rule logic
   Create one reusable function that checks a single file.
3. Add structured findings
   Return a finding with file_path, rule, severity, and message.
4. Add a few basic rules
   Examples: TODO, bare except:, print() left in code.
5. Analyze a real local project folder
   Read selected project files instead of manually pasting code.
6. Ignore irrelevant folders
   Skip .venv, .git, __pycache__, and similar generated folders.
7. Add automated tests
   Verify each rule and API response keeps working after changes.
8. Add a simple web page
   Let a user choose a project, run analysis, and view findings without Swagger.
9. Add AI-based review
   Use an LLM to explain issues and suggest improvements.
10. Save analysis history
       Add a database only when you need saved reports, users, or repeated project runs.
We are currently finishing feature 1.