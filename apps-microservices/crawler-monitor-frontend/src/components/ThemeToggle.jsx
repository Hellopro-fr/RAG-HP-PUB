import { Moon, Sun, Monitor } from 'lucide-react';
import { Button } from './ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { useTheme } from './providers/ThemeProvider';

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const Icon = resolvedTheme === 'dark' ? Moon : Sun;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Changer le thème">
          <Icon className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => setTheme('light')} data-selected={theme === 'light'}>
          <Sun className="h-4 w-4" /> Clair
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setTheme('dark')} data-selected={theme === 'dark'}>
          <Moon className="h-4 w-4" /> Sombre
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setTheme('system')} data-selected={theme === 'system'}>
          <Monitor className="h-4 w-4" /> Système
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
