// Helpers for the tool (MCP) form: a command is typed as one line and variables as one KEY=value per line.

/** "npx -y @scope/server" from a stored command and its arguments (quoting any argument that has a space) */
export const commandLine = (command: string, args: string[]) =>
  [command, ...args.map((a) => (/[\s"]/.test(a) ? `"${a.replace(/(["\\])/g, '\\$1')}"` : a))].join(' ')

export function parseEnv(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const i = line.indexOf('=')
    if (i > 0 && line.trim()) out[line.slice(0, i).trim()] = line.slice(i + 1).trim()
  }
  return out
}

export const formatEnv = (env: Record<string, string>) =>
  Object.entries(env)
    .map(([k, v]) => `${k}=${v}`)
    .join('\n')

export const isVariableName = (name: string) => /^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(name)
