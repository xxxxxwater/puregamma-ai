import type { CommandDefinition } from "../contracts";

/**
 * ctx.commands — a thin command registry (id -> handler). Phase 1 exposes
 * it for programmatic use (runPluginCommand); a command palette UI can be
 * added later without changing the plugin contract.
 */
export class CommandsService {
  private commands = new Map<string, CommandDefinition>();

  register(definition: CommandDefinition): () => void {
    this.commands.set(definition.id, definition);
    return () => {
      if (this.commands.get(definition.id) === definition) {
        this.commands.delete(definition.id);
      }
    };
  }

  list(): CommandDefinition[] {
    return [...this.commands.values()];
  }

  async run(id: string): Promise<boolean> {
    const command = this.commands.get(id);
    if (!command) return false;
    await command.run();
    return true;
  }
}

export const commands = new CommandsService();

export function runPluginCommand(id: string): Promise<boolean> {
  return commands.run(id);
}
