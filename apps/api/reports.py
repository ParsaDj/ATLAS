"""Printable customer reports rendered from authorized ATLAS records."""

from html import escape


def text(value) -> str:
    if value is None or value == "":
        return "Not recorded"
    return escape(str(value))


def table(rows: list[tuple[str, object]]) -> str:
    return "<table>" + "".join(
        f"<tr><th>{text(label)}</th><td>{text(value)}</td></tr>"
        for label, value in rows
    ) + "</table>"


def page(title: str, generated_at: str, generated_for: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{text(title)}</title><style>
body{{font:14px/1.55 system-ui,sans-serif;color:#243229;max-width:900px;margin:40px auto;padding:0 24px}}
h1{{font-size:28px}}h2{{font-size:18px;margin-top:30px;border-bottom:1px solid #ccd7c7;padding-bottom:7px}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #dce4d8;padding:9px;text-align:left;vertical-align:top}}th{{width:190px;background:#f3f6ef}}
.notice{{background:#f3f6ef;border-left:4px solid #718b65;padding:12px}}code{{overflow-wrap:anywhere}}ul{{padding-left:22px}}
footer{{margin-top:36px;color:#667565;font-size:12px}}@media print{{body{{margin:0;max-width:none}}}}
</style></head><body><header><p>ATLAS · Northstar Industries · Synthetic environment</p>
<h1>{text(title)}</h1><p>Generated {text(generated_at)} for {text(generated_for)}</p></header>
{body}<footer>This report describes synthetic test records. It does not establish physical robot safety or real-world equipment condition.</footer>
</body></html>"""


def incident_report(
    incident: dict,
    mission: dict | None,
    events: list[dict],
    investigation: dict,
    tickets: list[dict],
    generated_at: str,
    generated_for: str,
) -> str:
    mission_rows = (
        table(
            [
                ("Mission ID", mission["id"]),
                ("Mission status", mission["status"]),
                ("Started", mission.get("started_at")),
                ("Ended", mission.get("ended_at")),
            ]
        )
        if mission
        else '<p class="notice">No mission is linked to this incident.</p>'
    )
    event_rows = "".join(
        "<tr>"
        f"<td><code>{text(event.get('event_id'))}</code></td>"
        f"<td>{text(event.get('occurred_at'))}</td>"
        f"<td>{text(event.get('battery'))}%</td>"
        f"<td>{text(event.get('sensor_status'))}</td>"
        f"<td>{text(event.get('navigation_status', 'ok'))}</td>"
        "</tr>"
        for event in events
    ) or '<tr><td colspan="5">No triggering telemetry event was recorded.</td></tr>'
    limitations = "".join(
        f"<li>{text(item)}</li>" for item in investigation["limitations"]
    )
    citations = "".join(
        f"<li><code>{text(item['type'])}:{text(item['id'])}</code></li>"
        for item in investigation["citations"]
    ) or "<li>No supporting citation available.</li>"
    ticket_rows = "".join(
        "<tr>"
        f"<td><code>{text(ticket['id'])}</code></td>"
        f"<td>{text(ticket['summary'])}</td>"
        f"<td>{text(ticket['status'])}</td>"
        f"<td>{text(ticket['assigned_technician'])}</td>"
        f"<td>{text(ticket.get('resolution'))}</td>"
        "</tr>"
        for ticket in tickets
    ) or '<tr><td colspan="5">No maintenance ticket recorded.</td></tr>'
    body = f"""
<section><h2>Recorded incident facts</h2>{table([
    ('Incident ID', incident['id']), ('Robot', incident['robot_id']),
    ('Fault type', incident['type']), ('Status', incident['status']),
    ('Detected', incident['detected_at']), ('Recorded resolution', incident.get('resolution')),
])}</section>
<section><h2>Linked mission</h2>{mission_rows}</section>
<section><h2>Triggering evidence</h2><table><thead><tr><th>Event ID</th><th>Occurred</th><th>Battery</th><th>Sensor</th><th>Navigation</th></tr></thead><tbody>{event_rows}</tbody></table></section>
<section><h2>Evidence-based investigation</h2><p class="notice"><strong>Confidence: {text(investigation['confidence'])}</strong><br>{text(investigation['finding'])}</p>
<h3>Recommended next step</h3><p>{text(investigation['recommended_next_step'])}</p><h3>Limitations</h3><ul>{limitations}</ul><h3>Citations</h3><ul>{citations}</ul></section>
<section><h2>Maintenance history</h2><table><thead><tr><th>Ticket</th><th>Work summary</th><th>Status</th><th>Technician</th><th>Resolution</th></tr></thead><tbody>{ticket_rows}</tbody></table></section>"""
    return page(
        f"Incident report · {incident['type'].replace('_', ' ')}",
        generated_at,
        generated_for,
        body,
    )


def mission_report(
    mission: dict,
    events: list[dict],
    incidents: list[dict],
    tickets: list[dict],
    generated_at: str,
    generated_for: str,
) -> str:
    waypoints = "".join(
        f"<li>Waypoint {index}: ({text(point['x'])}, {text(point['y'])})</li>"
        for index, point in enumerate(mission["waypoints"], 1)
    )
    incident_rows = "".join(
        "<tr>"
        f"<td><code>{text(item['id'])}</code></td><td>{text(item['type'])}</td>"
        f"<td>{text(item['status'])}</td><td>{text(item['detected_at'])}</td>"
        "</tr>"
        for item in incidents
    ) or '<tr><td colspan="4">No incident recorded.</td></tr>'
    ticket_rows = "".join(
        "<tr>"
        f"<td><code>{text(item['id'])}</code></td><td>{text(item['summary'])}</td><td>{text(item['status'])}</td>"
        f"<td>{text(item['assigned_technician'])}</td><td>{text(item.get('resolution'))}</td>"
        "</tr>"
        for item in tickets
    ) or '<tr><td colspan="5">No maintenance ticket recorded.</td></tr>'
    batteries = [event["battery"] for event in events if event.get("battery") is not None]
    body = f"""
<section><h2>Mission facts</h2>{table([
    ('Mission ID', mission['id']), ('Robot', mission['robot_id']), ('Status', mission['status']),
    ('Replacement for mission', mission.get('replacement_for_mission_id')),
    ('Source incident', mission.get('source_incident_id')),
    ('Created', mission['created_at']), ('Started', mission.get('started_at')), ('Ended', mission.get('ended_at')),
    ('Completed waypoints', f"{mission.get('completed_waypoints', 0)} of {len(mission['waypoints'])}"),
    ('Cancellation reason', mission.get('cancellation_reason')),
])}</section>
<section><h2>Inspection route</h2><ol>{waypoints}</ol></section>
<section><h2>Telemetry summary</h2>{table([
    ('Recorded events', len(events)), ('First event', events[-1].get('occurred_at') if events else None),
    ('Last event', events[0].get('occurred_at') if events else None),
    ('Minimum battery', f"{min(batteries):g}%" if batteries else None),
])}</section>
<section><h2>Incident history</h2><table><thead><tr><th>Incident</th><th>Type</th><th>Status</th><th>Detected</th></tr></thead><tbody>{incident_rows}</tbody></table></section>
<section><h2>Maintenance history</h2><table><thead><tr><th>Ticket</th><th>Work summary</th><th>Status</th><th>Technician</th><th>Resolution</th></tr></thead><tbody>{ticket_rows}</tbody></table></section>"""
    return page(
        f"Inspection mission report · {mission['id']}",
        generated_at,
        generated_for,
        body,
    )
