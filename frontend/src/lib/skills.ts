// Helpers for editing a skill's SKILL.md. The server checks the file; this only saves people from the most common slip.

export const skillTemplate = (name = 'my-skill') =>
  `---\nname: ${name}\ndescription: What this skill does and when the agent should use it\n---\n\nSay here how the agent should work when this skill applies.\n`

/** the name line at the top of the file is made to match the skill's name, so a new skill can be named in one place */
export function withName(content: string, name: string): string {
  const match = content.match(/^(\uFEFF?---\r?\n)([\s\S]*?)(\r?\n---)/)
  if (!match) return content
  const head = match[2]
  const updated = /^name:/m.test(head) ? head.replace(/^name:.*$/m, `name: ${name}`) : `name: ${name}\n${head}`
  return content.replace(match[0], `${match[1]}${updated}${match[3]}`)
}

export const isSkillName = (name: string) => /^[a-z0-9][a-z0-9-]{0,39}$/.test(name)
