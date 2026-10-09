// Interactive release review uses only a fresh, expiring sample workspace.
const { chromium } = require("playwright"),
  assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
const base = process.env.TEST_WEB_URL || "http://localhost:3002",
  out =
    process.env.TEST_SCREENSHOT_DIR ||
    path.resolve(__dirname, "../../artifacts/release/journey");
fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true }),
    context = await browser.newContext({
      viewport: { width: 1440, height: 950 },
    }),
    page = await context.newPage(),
    report = { states: [], errors: [], interactions: [] };
  page.on("response", async (r) => {
    if (r.url().includes("/api/") && r.status() >= 400)
      console.log(
        "API error",
        r.status(),
        r.url(),
        await r.text().catch(() => ""),
      );
  });
  page.on("pageerror", (e) => report.errors.push(e.message));
  const go = async (p) => {
    console.log("Review", p);
    await page.goto(base + p);
    await page.waitForLoadState("networkidle");
  };
  const wait = async (l) => l.waitFor({ state: "visible", timeout: 180000 });
  const button = (n) => page.getByRole("button", { name: n, exact: true });
  const call = async (p, body) => {
    const r =
      body === undefined
        ? await page.request.get(base + "/api" + p)
        : await page.request.post(base + "/api" + p, {
            data: body,
            headers: { Origin: base },
          });
    const d = await r.json();
    assert(r.ok(), JSON.stringify({ p, status: r.status(), d }));
    return d;
  };
  const local = () => {
    const d = new Date();
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 19);
  };
  const capture = async (name) => {
    await page.screenshot({
      path: path.join(out, name + ".png"),
      fullPage: true,
      animations: "disabled",
    });
    const target=name.startsWith("case-")?page.locator(".evidence-workflow"):name.startsWith("records-")?page.locator(".monitoring-visits"):name.startsWith("procedure-")?page.locator(".evaluation-dashboard"):page.getByText("Measured workflow activity",{exact:true});
    if(await target.count()){await target.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,name+"-viewport.png"),fullPage:false,animations:"disabled"});}
    const measurements = await page.evaluate(() => {
      const rgba = (s) => (s.match(/[\d.]+/g) || []).map(Number),
        blend = (a, b) =>
          a
            .slice(0, 3)
            .map((v, i) => v * (a[3] ?? 1) + b[i] * (1 - (a[3] ?? 1))),
        lum = (c) =>
          c
            .map((v) => {
              v /= 255;
              return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
            })
            .reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
      const issues = [];
      let measured = 0;
      const walk = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
      );
      let n;
      while ((n = walk.nextNode())) {
        const e = n.parentElement,
          text = n.textContent.trim();
        if (
          !text ||
          !e ||
          e.closest("script,style,svg,option,[hidden]") ||
          (text === "✳" && e.closest(".wordmark"))
        )
          continue;
        const s = getComputedStyle(e),
          r = e.getBoundingClientRect();
        if (!r.width || !r.height || s.visibility === "hidden") continue;
        const range = document.createRange();
        range.selectNodeContents(n);
        if (!range.getBoundingClientRect().width) continue;
        const size = parseFloat(s.fontSize);
        if (size < 15)
          issues.push({ kind: "text-size", text: text.slice(0, 50), size });
        const chain = [];
        for (let p = e; p; p = p.parentElement) chain.unshift(p);
        let bg = [255, 255, 255],
          uncertain = false;
        for (const p of chain) {
          const st = getComputedStyle(p);
          if (st.backgroundImage !== "none" || st.opacity !== "1")
            uncertain = true;
          bg = blend(rgba(st.backgroundColor), bg);
        }
        if (!uncertain) {
          const l1 = lum(blend(rgba(s.color), bg)),
            l2 = lum(bg),
            ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05),
            threshold =
              size >= 24 || (size >= 18.66 && parseInt(s.fontWeight) >= 700)
                ? 3
                : 4.5;
          measured++;
          if (ratio < threshold && !e.closest(":disabled"))
            issues.push({ kind: "contrast", text: text.slice(0, 50), ratio });
        }
      }
      for (const e of document.querySelectorAll(
        "button,input:not([type=checkbox]):not([type=radio]),select,textarea,a.button",
      )) {
        if (e.closest("[hidden]")) continue;
        const r = e.getBoundingClientRect();
        if (r.width && r.height && r.height < 43.9)
          issues.push({
            kind: "control-height",
            text: e.textContent.slice(0, 50),
            height: r.height,
          });
      }
      return {
        width: innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        measured,
        issues,
      };
    });
    report.states.push({ name, ...measurements });
  };
  try {
    await go("/");
    await button("Explore a sample case").first().click();
    await page.waitForURL("**/workspace");
    await page.waitForLoadState("networkidle");
    report.workspace = (await call("/auth/me")).workspace_id;
    await button("I reviewed this step · continue").click();
    await page.reload();
    await wait(
      page.getByRole("heading", { name: "Sample walkthrough · 2 of 6" }),
    );
    await button("Skip walkthrough").click();
    await button("Resume sample walkthrough").click();
    report.interactions.push(
      "Walkthrough progress persists and resumes after skipping",
    );
    await go("/workspace/settings");
    await button("Data policy").click();
    await page
      .getByLabel("Observation freshness limit (hours)", { exact: false })
      .fill("24");
    await page.getByLabel("Reminder scan frequency (minutes)").fill("15");
    await page
      .getByLabel("Monitoring-visit checklist template")
      .fill("Review current request owners\nReview unresolved exceptions");
    await button("Save workspace policy").click();
    await wait(
      page.getByRole("status").filter({ hasText: "Preferences saved." }),
    );
    await go("/workspace/cases/CASE-4");
    await button("Run investigation").click();
    await wait(
      page.getByRole("heading", {
        name: "Investigation findings",
        exact: true,
      }),
    );
    await page
      .getByLabel("Review notes", { exact: true })
      .fill(
        "Human reviewer checked exact procedure citations and historical observations.",
      );
    await button("Approve recommendation").click();
    await wait(page.getByText("approved by Sample visitor", { exact: true }));
    await button("Suggest investigation checks").click();
    await wait(
      page.getByText("Draft · suggestions for human review", { exact: true }),
    );
    const checkFields = page.locator(".evidence-workflow").locator("textarea");
    await checkFields
      .first()
      .fill(
        "Personally verify the current synchronization receipt and destination binder record.",
      );
    assert(await button("Activate reviewed checklist").isDisabled());
    await button("Save checklist").click();
    await wait(
      page.getByRole("status").filter({ hasText: "Checklist saved." }),
    );
    await button("Activate reviewed checklist").click();
    await wait(page.getByText("Human-reviewed checklist", { exact: true }));
    await button("Information requests").click();
    await page
      .getByLabel("Request title", { exact: true })
      .fill("Current synchronization evidence");
    await page
      .getByLabel("Requested items", { exact: true })
      .fill("Current synchronization receipt\nDestination binder visibility");
    await button("Save request draft").click();
    await wait(
      page
        .getByRole("status")
        .filter({ hasText: "Information request draft saved." }),
    );
    const req = page.locator(".request-detail");
    await req.locator("summary").first().click();
    await req
      .getByLabel("Request status", { exact: false })
      .selectOption("requested");
    await req
      .getByRole("button", { name: "Save request update", exact: true })
      .click();
    await wait(
      page.getByRole("status").filter({ hasText: "Request updated." }),
    );
    await button("Supporting observations").click();
    await page
      .getByLabel("Observation and evidence summary", { exact: true })
      .fill(
        "Personally reviewed the current synthetic synchronization receipt and destination binder visibility.",
      );
    await page.getByLabel("Observation time", { exact: true }).fill(local());
    await button("Record observation").click();
    await wait(
      page
        .getByRole("status")
        .filter({ hasText: "Supporting observation recorded." }),
    );
    let data = await call("/cases/CASE-4/workflow"),
      evidence = data.evidence[0];
    await button("Checks").click();
    const checkRegion = page.locator(".evidence-workflow");
    const states = checkRegion.getByLabel("Check state", { exact: true }),
      refs = checkRegion.getByLabel("Supporting evidence", { exact: true });
    assert((await states.count()) > 0, "Active check controls must be present");
    for (let i = 0; i < (await states.count()); i++) {
      await states.nth(i).selectOption("verified");
      await refs.nth(i).selectOption(evidence.id);
      await checkRegion
        .getByLabel("Check notes", { exact: true })
        .nth(i)
        .fill("Manually verified current synthetic records and receipt.");
    }
    await button("Save checklist").click();
    await wait(
      page.getByRole("status").filter({ hasText: "Checklist saved." }),
    );
    await button("Information requests").click();
    await req.locator("summary").first().click();
    await req
      .getByLabel("Request status", { exact: false })
      .selectOption("received");
    await req
      .getByLabel("Response received", { exact: true })
      .fill("Current synthetic receipt and binder visibility reviewed.");
    await req
      .getByLabel("Response evidence references", { exact: true })
      .selectOption(evidence.id);
    await req
      .getByRole("button", { name: "Save request update", exact: true })
      .click();
    await wait(
      page.getByRole("status").filter({ hasText: "Request updated." }),
    );
    await button("Human effort").click();
    await page.getByLabel("Human work minutes").fill("8.5");
    await page
      .getByLabel("Effort notes", { exact: true })
      .fill("Explicit actual synthetic review effort.");
    await button("Record human effort").click();
    await wait(
      page.getByRole("status").filter({ hasText: "Human effort recorded." }),
    );
    const history = await call(
        "/operations/history?study_id=CT-204&site_id=SITE-104",
      ),
      updated = await call("/walkthrough/updated-records", {});
    await go("/workspace/cases/CASE-4");
    await button("Comparisons & related cases").click();
    await page.getByLabel("Earlier snapshot").selectOption(history[0].id);
    await page.getByLabel("Later snapshot").selectOption(updated.snapshot_id);
    await button("Compare snapshots").click();
    await wait(
      page
        .getByRole("status")
        .filter({ hasText: "Observation comparison saved." }),
    );
    const link = page
      .getByRole("button", { name: /Review link to CASE-/ })
      .first();
    if (await link.count()) {
      await link.click();
      await page
        .getByLabel("Reason for linking")
        .fill(
          "Reviewer confirmed similar binder symptoms and relevant differences.",
        );
      await page
        .getByRole("checkbox", {
          name: "I reviewed the differences and confirm this link.",
        })
        .check();
      await button("Confirm related-case link").click();
      await wait(
        page
          .getByRole("status")
          .filter({ hasText: "Human-confirmed case link saved." }),
      );
    }
    report.interactions.push(
      "Human review/activation, information response, current observation, verified checks, actual effort, record comparison and confirmed link",
    );
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 950 });
      for (const name of [
        "Checks",
        "Information requests",
        "Supporting observations",
        "Comparisons & related cases",
        "Human effort",
      ]) {
        await button(name).click();
        await capture("case-" + name.replaceAll(" ", "-") + "-" + width);
      }
    }
    await page.setViewportSize({ width: 1440, height: 950 });
    await page
      .getByLabel("Resolution note", { exact: true })
      .fill(
        "Reviewer verified current synthetic binder records and completed all assessed checks.",
      );
    await page
      .getByLabel("Resolution supporting evidence", { exact: true })
      .selectOption(evidence.id);
    await page
      .getByLabel("Current verification time", { exact: true })
      .fill(local());
    await page
      .getByRole("checkbox", { name: /I verified current status/ })
      .check();
    await button("Mark case resolved").click();
    await wait(page.getByText("Case marked resolved.", { exact: true }));
    const pdfWait = page.waitForEvent("download");
    await page
      .getByRole("link", { name: "Case package PDF", exact: true })
      .click();
    await (await pdfWait).saveAs(path.join(out, "case-package.pdf"));
    const jsonWait = page.waitForEvent("download");
    await button("Case package JSON").click();
    await (await jsonWait).saveAs(path.join(out, "case-package.json"));
    assert(
      JSON.parse(fs.readFileSync(path.join(out, "case-package.json"))).checks
        .length,
    );
    await page
      .getByLabel("Reason for reopening", { exact: true })
      .fill("Reopened for a fresh synthetic current-record verification.");
    await button("Reopen case").click();
    await wait(
      page.getByText(
        "Case reopened; the original resolution remains in activity.",
        { exact: true },
      ),
    );
    report.interactions.push(
      "Separate current-evidence resolution, complete PDF/JSON exports and preserved reopening history",
    );
    // The rapid screenshot journey can exhaust the real 180/min session budget.
    // Allow its window to renew before continuing; keep production limits intact.
    await page.waitForTimeout(61000);
    await go("/workspace/operations");
    await page
      .getByText("Preview CSV/JSON record import", { exact: true })
      .click();
    await button("Load generic import example").click();
    await page.waitForFunction(()=>document.querySelector(".bulk-import textarea")?.value.includes("snapshot_id"));
    await button("Validate import preview").click();
    await wait(
      page.getByRole("heading", { name: "2 accepted rows · 0 rejected rows" }),
    );
    await page
      .getByRole("checkbox", {
        name: /I reviewed the accepted and rejected rows/,
      })
      .check();
    await button("Commit accepted snapshots").click();
    await wait(
      page
        .getByRole("status")
        .filter({ hasText: "Accepted snapshots imported." }),
    );
    await page
      .getByText("Monitoring-visit preparation", { exact: true })
      .click();
    await page
      .getByLabel("Preparation title")
      .fill("Sample monitoring preparation");
    await page.getByLabel("Visit study").selectOption("CT-204");
    await page.getByLabel("Visit site").selectOption("SITE-104");
    await page.getByLabel("Visit date", { exact: true }).fill(local());
    await button("Create preparation view").click();
    await wait(
      page
        .getByRole("status")
        .filter({ hasText: "Dated preparation view created." }),
    );
    await page
      .getByLabel("Preparation check state")
      .first()
      .selectOption("needs_follow_up");
    await page
      .getByLabel("Preparation check notes")
      .first()
      .fill("Reviewer to confirm current records before the visit.");
    await button("Save preparation checklist").click();
    await wait(
      page
        .getByRole("status")
        .filter({ hasText: "Preparation checklist saved." }),
    );
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 950 });
      await capture("records-preparation-" + width);
    }
    report.interactions.push(
      "Preview/confirm import and editable dated monitoring preparation",
    );
    const k = (await call("/knowledge")).find((k) => k.id === "KB-004");
    await call("/knowledge/KB-004", {
      title: k.title,
      category: k.category,
      content:
        k.content + " Verify updated records with the assigned reviewer.",
      expected_version: k.version,
    });
    await go("/workspace/knowledge");
    await page.getByText(/Procedure changes and reassessment ·/).click();
    await page
      .locator("details")
      .filter({ has: page.getByLabel("Reassessment decision") })
      .last()
      .locator("summary")
      .first()
      .click();
    await page
      .getByLabel("Reassessment decision")
      .first()
      .selectOption("needed");
    await page
      .getByLabel("Reassessment rationale")
      .first()
      .fill(
        "The changed procedure needs a new review of current observations.",
      );
    await button("Record reassessment").first().click();
    await wait(
      page.getByRole("status").filter({ hasText: "Reassessment recorded." }),
    );
    await page.getByText("AI evaluation dashboard", { exact: true }).click();
    await page.getByLabel("Evaluation mode").selectOption("procedure");
    await button("Run isolated scenario evaluation").click();
    await wait(page.getByText(/procedure-matcher · completed/));
    await page.getByText(/procedure-matcher · completed/).click();
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 950 });
      await capture("procedure-evaluation-" + width);
    }
    report.interactions.push(
      "Procedure-change reassessment and actual worker evaluation results",
    );
    await go("/workspace");
    await page.getByText(/In-app follow-up reminders ·/).click();
    await page.getByText("Measured workflow activity", { exact: true }).click();
    await wait(page.getByText("Explicit human effort", { exact: true }));
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 950 });
      await capture("overview-measurements-" + width);
    }
    assert.deepEqual(report.errors, []);
    for (const state of report.states) {
      assert(
        state.scrollWidth <= state.width + 1,
        state.name + " page overflow",
      );
      assert.deepEqual(state.issues, [], state.name + " measurement issues");
    }
  } catch (error) {
    await page.screenshot({
      path: path.join(out, "failure.png"),
      fullPage: true,
    });
    fs.writeFileSync(
      path.join(out, "failure.txt"),
      await page.locator("body").innerText(),
    );
    throw error;
  } finally {
    fs.writeFileSync(
      path.join(out, "review.json"),
      JSON.stringify(report, null, 2),
    );
    await browser.close();
  }
  console.log(
    JSON.stringify(
      {
        states: report.states.length,
        measuredText: report.states.reduce((s, p) => s + p.measured, 0),
        interactions: report.interactions,
      },
      null,
      2,
    ),
  );
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
