(function () {
  function $(selector) {
    return document.querySelector(selector);
  }

  function loadReport() {
    const container = document.getElementById("report-data");
    if (!container) {
      return null;
    }
    try {
      return JSON.parse(container.textContent || "{}");
    } catch (error) {
      console.error("Failed to parse report JSON", error);
      return null;
    }
  }

  function mapProjects(report) {
    return new Map(
      (report.projects || []).map((project) => [
        project.project.path_with_namespace,
        project.metrics,
      ]),
    );
  }

  function mapPeople(report) {
    return new Map(
      (report.people || []).map((person) => [person.user.username, person.metrics]),
    );
  }

  function updateTable(rows, lookup, windowKey) {
    rows.forEach((row) => {
        const name = row.dataset.name;
        const metrics = lookup.get(name);
        if (!metrics) {
          return;
        }
        const windowMetrics = metrics[windowKey] || {
          merge_requests_created: 0,
          merge_requests_merged: 0,
          merge_requests_closed: 0,
          comments_written: 0,
        };
      row.querySelectorAll(".metric").forEach((cell) => {
          const field = cell.dataset.field;
          if (Object.prototype.hasOwnProperty.call(windowMetrics, field)) {
            cell.textContent = windowMetrics[field];
          }
        });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const report = loadReport();
    if (!report) {
      return;
    }
    const windowSelect = $("#window-select");
    if (!windowSelect) {
      return;
    }
    const projectRows = Array.from(document.querySelectorAll("[data-table=projects] [data-entity=project]"));
    const peopleRows = Array.from(document.querySelectorAll("[data-table=people] [data-entity=person]"));
    const projectMetrics = mapProjects(report);
    const peopleMetrics = mapPeople(report);

    function refresh() {
      const windowKey = windowSelect.value;
      updateTable(projectRows, projectMetrics, windowKey);
      updateTable(peopleRows, peopleMetrics, windowKey);
    }

    windowSelect.addEventListener("change", refresh);
    refresh();
  });
})();
