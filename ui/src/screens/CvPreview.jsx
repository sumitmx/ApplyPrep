export default function CvPreview({ content, accentHex, accentInk, accentText, layout }) {
  const identity = content.identity || {}
  const contact = [identity.location, identity.phone, identity.email, identity.linkedin]
    .filter(Boolean).join(' | ')

  return (
    <div
      className="cv-preview"
      style={{
        '--cv-accent': accentHex,
        '--cv-ink': accentInk || '#fff',
        '--cv-accent-text': accentText || accentHex,
        ...(layout || {}),
      }}
    >
      <div className="cv-header">
        <div className="cv-name">{identity.name}</div>
        {identity.headline && <div className="cv-headline">{identity.headline}</div>}
        {contact && <div className="cv-contact">{contact}</div>}
      </div>

      {content.summary && (
        <>
          <div className="cv-heading">PROFESSIONAL SUMMARY</div>
          <p className="cv-body">{content.summary}</p>
        </>
      )}

      {(content.sections || []).map((section, i) => (
        <div key={i}>
          <div className="cv-heading">{section.heading}</div>

          {section.kind === 'skills' && section.tiers.map((tier) => (
            <p className="cv-body" key={tier.label}>
              <span className="cv-accent-text">{tier.label}: </span>
              {tier.items.join(', ')}
            </p>
          ))}

          {section.kind === 'experience' && section.roles.map((role, ri) => (
            <div key={ri} className="cv-role">
              <p className="cv-roleline">
                <b>{role.title}</b>, <span className="cv-accent-text">{role.company}</span>
              </p>
              {role.client && <p className="cv-client">Client: {role.client}</p>}
              <p className="cv-meta">
                {role.location ? role.location + '    ' : ''}{role.period}
              </p>
              <ul className="cv-bullets">
                {role.bullets.map((b, bi) => <li key={bi}>{b}</li>)}
              </ul>
            </div>
          ))}

          {section.kind === 'projects' && (
            <ul className="cv-bullets">
              {section.items.map((item, ii) => (
                <li key={ii}><b>{item.name}:</b> {item.text}</li>
              ))}
            </ul>
          )}

          {section.kind === 'education' && section.items.map((item, ii) => (
            <p className="cv-body" key={ii}>
              <b>{item.degree}</b>  -  {item.school} ({item.years})
            </p>
          ))}

          {section.kind === 'certifications' && (
            <ul className="cv-bullets">
              {section.items.map((item, ii) => <li key={ii}>{item}</li>)}
            </ul>
          )}

          {section.kind === 'languages' && (
            <ul className="cv-bullets">
              {section.items.map((l, ii) => (
                <li key={ii}>{l.level ? l.name + ' (' + l.level + ')' : l.name}</li>
              ))}
            </ul>
          )}

          {section.kind === 'highlights' && (
            <ul className="cv-bullets">
              {section.items.map((item, ii) => {
                // Older drafts stored highlights as plain strings.
                const topic = typeof item === 'object' ? item.topic : null
                const text = typeof item === 'object' ? item.text : item
                return <li key={ii}>{topic && <b>{topic} - </b>}{text}</li>
              })}
            </ul>
          )}
        </div>
      ))}
    </div>
  )
}
