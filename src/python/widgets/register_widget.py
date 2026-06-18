from __future__ import annotations

import customtkinter as ctk


SURFACE = "#0E1A1E"
SURFACE_ALT = "#14272D"
BORDER = "#21434B"
TEXT = "#EAF2F5"
MUTED = "#83A0A8"
CYAN = "#00D9FF"
OFF = "#22333A"


class MetricWidget(ctk.CTkFrame):
    def __init__(self, master, title: str, value: str = "--", accent: str = CYAN):
        super().__init__(
            master,
            fg_color=SURFACE_ALT,
            border_color=BORDER,
            border_width=1,
            corner_radius=7,
        )
        self.grid_columnconfigure(0, weight=1)
        self._accent = accent

        self.title_label = ctk.CTkLabel(
            self,
            text=title,
            text_color=MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.title_label.grid(row=0, column=0, sticky="w", padx=12, pady=(9, 0))

        self.value_label = ctk.CTkLabel(
            self,
            text=value,
            text_color=accent,
            font=ctk.CTkFont(family="Consolas", size=21, weight="bold"),
        )
        self.value_label.grid(row=1, column=0, sticky="w", padx=12, pady=(1, 9))

    def set(self, value: str, color: str | None = None) -> None:
        self.value_label.configure(text=value, text_color=color or self._accent)


class ByteRegisterWidget(ctk.CTkFrame):
    def __init__(self, master, title: str):
        super().__init__(
            master,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
            corner_radius=7,
        )
        self.grid_columnconfigure(1, weight=1)
        self._value = 0

        self.name_label = ctk.CTkLabel(
            self,
            text=title,
            width=68,
            text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
        )
        self.name_label.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=8)

        bit_header = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        bit_header.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(7, 1))
        bit_header.grid_columnconfigure(tuple(range(8)), weight=1, uniform="bits")

        bit_row = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        bit_row.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(1, 8))
        bit_row.grid_columnconfigure(tuple(range(8)), weight=1, uniform="bits")

        self.bit_labels: list[ctk.CTkLabel] = []
        for column, bit in enumerate(range(7, -1, -1)):
            ctk.CTkLabel(
                bit_header,
                text=str(bit),
                text_color=MUTED,
                font=ctk.CTkFont(size=10),
                height=14,
            ).grid(row=0, column=column, sticky="ew")

            label = ctk.CTkLabel(
                bit_row,
                text="0",
                height=28,
                corner_radius=4,
                fg_color=OFF,
                text_color=MUTED,
                font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            )
            label.grid(row=0, column=column, sticky="ew", padx=2)
            self.bit_labels.append(label)

        self.value_label = ctk.CTkLabel(
            self,
            text="0x00\n000",
            width=62,
            text_color=CYAN,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
        )
        self.value_label.grid(row=0, column=2, rowspan=2, padx=(2, 10), pady=8)

    def set_value(self, value: int) -> None:
        self._value = value & 0xFF
        for label, bit in zip(self.bit_labels, range(7, -1, -1)):
            active = bool(self._value & (1 << bit))
            label.configure(
                text="1" if active else "0",
                fg_color=CYAN if active else OFF,
                text_color="#031014" if active else MUTED,
            )
        self.value_label.configure(text=f"0x{self._value:02X}\n{self._value:03d}")
