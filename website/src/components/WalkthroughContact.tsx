const email = 'alexey.khabalov@gmail.com';
const subject = 'LOB Arena walkthrough request';
const body = [
  'Hi Alexey,',
  '',
  "I'd like a guided walkthrough of LOB Arena.",
  '',
  'Organization:',
  "What I'd like to explore:",
  '',
  'Thanks,',
].join('\n');
const emailHref = `mailto:${email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;

export function WalkthroughContact() {
  return (
    <section id="contact" className="panel walkthrough-contact" tabIndex={-1} aria-labelledby="contact-title">
      <p className="eyebrow">REQUEST A WALKTHROUGH</p>
      <h2 id="contact-title">See LOB Arena in action</h2>
      <p>Request a guided walkthrough of the research platform, or discuss your detector-validation needs.</p>
      <p>Tell me a little about your organization and what you would like to explore.</p>
      <div className="contact-details">
        <div><strong>Alexey Khabalov</strong><span>Creator of LOB Arena</span></div>
        <a className="button secondary contact-email" href={emailHref}>{email}</a>
        <a className="text-link" href="https://www.linkedin.com/in/khabalov/" aria-label="Alexey Khabalov on LinkedIn">LinkedIn ↗</a>
      </div>
      <p className="caption contact-note">Opens your email app with a draft you can edit before sending.</p>
    </section>
  );
}
