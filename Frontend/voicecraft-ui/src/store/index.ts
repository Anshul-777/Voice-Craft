import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface User { id: string; email: string; username: string; plan: string; }

interface AuthStore {
  token: string | null;
  user: User | null;
  setAuth: (token: string, user: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => {
        localStorage.setItem('vc_token', token);
        set({ token, user });
      },
      logout: () => {
        localStorage.removeItem('vc_token');
        set({ token: null, user: null });
      },
    }),
    { name: 'vc-auth' }
  )
);

interface ToastItem { id: string; message: string; type: 'success' | 'error' | 'info'; }
interface ToastStore {
  toasts: ToastItem[];
  addToast: (message: string, type?: ToastItem['type']) => void;
  removeToast: (id: string) => void;
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  addToast: (message, type = 'info') => {
    const id = Math.random().toString(36).slice(2);
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 4000);
  },
  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

interface ThemeStore {
  isDark: boolean;
  toggleTheme: () => void;
  setTheme: (isDark: boolean) => void;
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set) => ({
      isDark: false, // Light mode by default
      toggleTheme: () => set((state) => ({ isDark: !state.isDark })),
      setTheme: (isDark) => set({ isDark }),
    }),
    { name: 'vc-theme' }
  )
);
