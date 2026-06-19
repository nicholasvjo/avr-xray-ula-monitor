from __future__ import annotations

import queue
import time
import tkinter as tk
from pathlib import Path
from typing import Any

import customtkinter as ctk

from protocol import (
    ATMEGA328P_SRAM_SIZE,
    FLAG_CARRY,
    FLAG_DIV_ZERO,
    FLAG_NEGATIVE,
    FLAG_OVERFLOW,
    FLAG_ZERO,
    HelloFrame,
    MemoryFrame,
    OPERATION_REFERENCE,
    SRAM_SIZE,
    SnapshotFrame,
    decode_eeprom_history,
    sram_description,
    sram_meaning,
)
from serial_worker import SerialWorker, SourceEvent, list_serial_ports
from simulator import SimulatorWorker
from widgets import ByteRegisterWidget, MemoryHeatmap, MetricWidget


BG = "#071013"
SURFACE = "#0E1A1E"
SURFACE_ALT = "#14272D"
BORDER = "#21434B"
TEXT = "#EAF2F5"
MUTED = "#83A0A8"
CYAN = "#00D9FF"
GREEN = "#3BEE7A"
AMBER = "#FFB84D"
RED = "#FF4F70"
BLUE = "#4C7DFF"
OFF = "#22333A"


class AvrXrayApp(ctk.CTk):
    def __init__(
        self,
        initial_port: str | None = None,
        baud: int = 115200,
        simulate: bool = False,
    ):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.initial_port = initial_port
        self.default_baud = baud
        self.events: queue.Queue[SourceEvent] = queue.Queue()
        self.source: SerialWorker | SimulatorWorker | None = None
        self.connection_state = "disconnected"
        self.latest_snapshot: SnapshotFrame | None = None
        self.latest_memory: MemoryFrame | None = None
        self._last_ports_render_at = 0.0
        self._ports_render_interval = 0.2
        self._last_memory_render_at = 0.0
        self._memory_render_interval = 0.2
        self._highlighted_operation: int | None = None

        self.port_var = tk.StringVar(value=initial_port or "Automática")
        self.baud_var = tk.StringVar(value=str(baud))
        self.simulate_var = tk.BooleanVar(value=simulate)
        self.status_var = tk.StringVar(value="Desconectado")
        self.device_var = tk.StringVar(value="Aguardando dispositivo")
        self.sequence_var = tk.StringVar(value="amostra --")
        self.uptime_var = tk.StringVar(value="tempo --")
        self.inspector_title_var = tk.StringVar(
            value="ula_probe[0] — Operando A da ULA"
        )
        self.inspector_var = tk.StringVar(
            value=(
                "Deslocamento na janela: 0x00\n"
                "Valor: 0 decimal  |  0x00 hexadecimal  |  00000000 binário\n\n"
                "O que representa:\n"
                "Guarda o valor de 4 bits confirmado como primeira entrada da operação."
            )
        )
        self.history_status_var = tk.StringVar(
            value="Aguardando a leitura da EEPROM."
        )

        self.title("Sistemas Digitais 2026.1")
        self.geometry("1380x900")
        self.minsize(1160, 760)
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.ula_metrics: dict[str, MetricWidget] = {}
        self.ula_flags: dict[str, ctk.CTkLabel] = {}
        self.sreg_flags: dict[str, ctk.CTkLabel] = {}
        self.port_widgets: dict[str, dict[str, ByteRegisterWidget]] = {}
        self.timer_metrics: dict[str, MetricWidget] = {}
        self.operation_reference_rows: dict[int, list[ctk.CTkLabel]] = {}
        self.history_rows: list[dict[str, ctk.CTkLabel]] = []

        self._build_layout()
        self._refresh_ports()
        self.after(50, self._poll_events)

        if simulate or initial_port:
            self.after(180, self._connect)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()

        self.tabview = ctk.CTkTabview(
            self,
            fg_color=BG,
            border_color=BORDER,
            border_width=1,
            segmented_button_fg_color=SURFACE,
            segmented_button_selected_color=CYAN,
            segmented_button_selected_hover_color="#00B8D9",
            segmented_button_unselected_color=OFF,
            segmented_button_unselected_hover_color="#314A54",
            text_color=TEXT,
        )
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 10))

        self.overview_tab = self.tabview.add("Visão Geral")
        self.ports_tab = self.tabview.add("Portas")
        self.timers_tab = self.tabview.add("Temporizadores")
        self.memory_tab = self.tabview.add("Memória")

        for tab in (
            self.overview_tab,
            self.ports_tab,
            self.timers_tab,
            self.memory_tab,
        ):
            tab.configure(fg_color=BG)

        self._build_overview_tab()
        self._build_ports_tab()
        self._build_timers_tab()
        self._build_memory_tab()

        footer = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 12))
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            footer,
            textvariable=self.status_var,
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            footer,
            textvariable=self.sequence_var,
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=12),
        ).grid(row=0, column=1, padx=14)
        ctk.CTkLabel(
            footer,
            textvariable=self.uptime_var,
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=12),
        ).grid(row=0, column=2)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 10))
        header.grid_columnconfigure(0, weight=1)

        brand = ctk.CTkFrame(header, fg_color=BG, corner_radius=0)
        brand.grid(row=0, column=0, rowspan=2, sticky="w")
        brand.grid_columnconfigure(1, weight=1)

        logo_path = Path(__file__).resolve().parents[2] / "assets" / "ufrj.png"
        try:
            self.ufrj_logo = tk.PhotoImage(file=str(logo_path)).subsample(5, 5)
            tk.Label(
                brand,
                image=self.ufrj_logo,
                width=64,
                height=76,
                bg=BG,
                borderwidth=0,
                highlightthickness=0,
            ).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 13))
        except tk.TclError:
            self.ufrj_logo = None
            ctk.CTkLabel(
                brand,
                text="UFRJ",
                width=64,
                height=64,
                corner_radius=6,
                fg_color=SURFACE,
                text_color=TEXT,
                font=ctk.CTkFont(size=17, weight="bold"),
            ).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 13))

        ctk.CTkLabel(
            brand,
            text="Sistemas Digitais 2026.1",
            text_color=TEXT,
            font=ctk.CTkFont(size=27, weight="bold"),
        ).grid(row=0, column=1, sticky="sw")
        ctk.CTkLabel(
            brand,
            textvariable=self.device_var,
            text_color=MUTED,
            font=ctk.CTkFont(size=13),
        ).grid(row=1, column=1, sticky="nw", pady=(2, 0))

        controls = ctk.CTkFrame(header, fg_color=BG, corner_radius=0)
        controls.grid(row=0, column=1, rowspan=2, sticky="e")

        self.port_combo = ctk.CTkComboBox(
            controls,
            variable=self.port_var,
            values=["Automática"],
            width=150,
            height=36,
            fg_color=SURFACE,
            border_color=BORDER,
            button_color=OFF,
            button_hover_color="#314A54",
            dropdown_fg_color=SURFACE,
        )
        self.port_combo.grid(row=0, column=0, padx=4)

        ctk.CTkButton(
            controls,
            text="Atualizar",
            command=self._refresh_ports,
            width=84,
            height=36,
            fg_color=OFF,
            hover_color="#314A54",
        ).grid(row=0, column=1, padx=4)

        self.baud_entry = ctk.CTkEntry(
            controls,
            textvariable=self.baud_var,
            width=90,
            height=36,
            fg_color=SURFACE,
            border_color=BORDER,
            justify="center",
        )
        self.baud_entry.grid(row=0, column=2, padx=4)

        self.simulate_switch = ctk.CTkSwitch(
            controls,
            text="Simular",
            variable=self.simulate_var,
            onvalue=True,
            offvalue=False,
            progress_color=BLUE,
            button_color=TEXT,
        )
        self.simulate_switch.grid(row=0, column=3, padx=(8, 6))

        self.connect_button = ctk.CTkButton(
            controls,
            text="Conectar",
            command=self._toggle_connection,
            width=112,
            height=36,
            fg_color=GREEN,
            hover_color="#2FC765",
            text_color="#04120A",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.connect_button.grid(row=0, column=4, padx=4)

        self.status_badge = ctk.CTkLabel(
            controls,
            text="DESCONECTADO",
            width=112,
            height=32,
            corner_radius=7,
            fg_color=OFF,
            text_color=MUTED,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.status_badge.grid(row=0, column=5, padx=(8, 0))

    def _build_overview_tab(self) -> None:
        tab = self.overview_tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        self.overview_scroll = ctk.CTkScrollableFrame(
            tab,
            fg_color=BG,
            corner_radius=0,
            scrollbar_button_color="#29505A",
            scrollbar_button_hover_color=CYAN,
        )
        self.overview_scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.overview_scroll.grid_columnconfigure(0, weight=1)

        summary = ctk.CTkFrame(
            self.overview_scroll,
            fg_color=BG,
            corner_radius=0,
        )
        summary.grid(row=0, column=0, sticky="ew")
        summary.grid_columnconfigure(0, weight=3)
        summary.grid_columnconfigure(1, weight=2)

        left = ctk.CTkFrame(
            summary,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
        )
        left.grid(row=0, column=0, sticky="nsew", padx=(6, 5), pady=6)
        left.grid_columnconfigure((0, 1, 2), weight=1, uniform="ula")

        ctk.CTkLabel(
            left,
            text="ULA 4 bits",
            text_color=TEXT,
            font=ctk.CTkFont(size=19, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 9))

        metric_specs = (
            ("a", "A"),
            ("b", "B"),
            ("operation", "Operação"),
            ("result", "Resultado"),
            ("input", "Entrada atual"),
            ("stage", "Etapa"),
        )
        for index, (key, title) in enumerate(metric_specs):
            widget = MetricWidget(left, title)
            widget.grid(
                row=1 + index // 3,
                column=index % 3,
                sticky="ew",
                padx=7,
                pady=7,
            )
            self.ula_metrics[key] = widget

        flag_frame = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0)
        flag_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=9, pady=(12, 14))
        flag_frame.grid_columnconfigure(tuple(range(5)), weight=1, uniform="flags")
        for column, name in enumerate(("Z", "C", "N", "V", "D")):
            label = ctk.CTkLabel(
                flag_frame,
                text=f"{name}\n0",
                height=58,
                corner_radius=6,
                fg_color=OFF,
                text_color=MUTED,
                font=ctk.CTkFont(size=16, weight="bold"),
            )
            label.grid(row=0, column=column, sticky="ew", padx=4)
            self.ula_flags[name] = label

        right = ctk.CTkFrame(
            summary,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
        )
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 6), pady=6)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right,
            text="Registrador de estado da CPU (SREG)",
            text_color=TEXT,
            font=ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        self.sreg_register = ByteRegisterWidget(right, "SREG")
        self.sreg_register.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

        sreg_frame = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0)
        sreg_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        sreg_frame.grid_columnconfigure(tuple(range(8)), weight=1, uniform="sreg")
        for column, name in enumerate(("I", "T", "H", "S", "V", "N", "Z", "C")):
            label = ctk.CTkLabel(
                sreg_frame,
                text=f"{name}\n0",
                height=43,
                corner_radius=5,
                fg_color=OFF,
                text_color=MUTED,
                font=ctk.CTkFont(size=12, weight="bold"),
            )
            label.grid(row=0, column=column, sticky="ew", padx=2)
            self.sreg_flags[name] = label

        ctk.CTkLabel(
            right,
            text="ADC A0",
            text_color=TEXT,
            font=ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=3, column=0, sticky="w", padx=16, pady=(12, 8))

        adc_metrics = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0)
        adc_metrics.grid(row=4, column=0, sticky="ew", padx=12)
        adc_metrics.grid_columnconfigure((0, 1), weight=1, uniform="adc")
        self.adc_raw = MetricWidget(adc_metrics, "Leitura", "0 / 1023")
        self.adc_raw.grid(row=0, column=0, sticky="ew", padx=4)
        self.adc_voltage = MetricWidget(adc_metrics, "Tensão", "0,000 V", GREEN)
        self.adc_voltage.grid(row=0, column=1, sticky="ew", padx=4)

        self.adc_bar = ctk.CTkProgressBar(
            right,
            height=18,
            fg_color=OFF,
            progress_color=GREEN,
            border_color=BORDER,
            border_width=1,
        )
        self.adc_bar.grid(row=5, column=0, sticky="ew", padx=16, pady=(12, 16))
        self.adc_bar.set(0)

        reference = ctk.CTkFrame(
            self.overview_scroll,
            fg_color=BG,
            corner_radius=0,
        )
        reference.grid(row=1, column=0, sticky="ew")
        reference.grid_columnconfigure(0, weight=3)
        reference.grid_columnconfigure(1, weight=2)

        operations_panel = ctk.CTkFrame(
            reference,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
        )
        operations_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(6, 5),
            pady=6,
        )
        operations_panel.grid_columnconfigure(0, weight=1)
        operations_panel.grid_columnconfigure(1, weight=1)
        operations_panel.grid_columnconfigure(2, weight=3)
        operations_panel.grid_columnconfigure(3, weight=2)
        operations_panel.grid_columnconfigure(4, weight=5)

        ctk.CTkLabel(
            operations_panel,
            text="Tabela de operações da ULA",
            text_color=TEXT,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(
            row=0,
            column=0,
            columnspan=5,
            sticky="w",
            padx=16,
            pady=(14, 4),
        )
        ctk.CTkLabel(
            operations_panel,
            text="O código usa os três bits menos significativos da entrada.",
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
        ).grid(
            row=1,
            column=0,
            columnspan=5,
            sticky="w",
            padx=16,
            pady=(0, 10),
        )

        headers = ("Código", "Binário", "Operação", "Expressão", "Descrição")
        for column, text in enumerate(headers):
            ctk.CTkLabel(
                operations_panel,
                text=text,
                height=30,
                fg_color="#18343C",
                text_color=CYAN,
                font=ctk.CTkFont(size=11, weight="bold"),
            ).grid(row=2, column=column, sticky="ew", padx=1, pady=1)

        for row, (code, binary, name, expression, description) in enumerate(
            OPERATION_REFERENCE,
            start=3,
        ):
            background = "#0A181D" if code % 2 == 0 else "#10242A"
            values = (str(code), binary, name, expression, description)
            labels: list[ctk.CTkLabel] = []
            for column, value in enumerate(values):
                label = ctk.CTkLabel(
                    operations_panel,
                    text=value,
                    height=31,
                    fg_color=background,
                    text_color=TEXT if column != 1 else CYAN,
                    anchor="w" if column >= 2 else "center",
                    font=(
                        ctk.CTkFont(
                            family="Consolas",
                            size=11,
                            weight="bold" if column == 0 else "normal",
                        )
                        if column in {0, 1, 3}
                        else ctk.CTkFont(
                            size=11,
                            weight="bold" if column == 2 else "normal",
                        )
                    ),
                )
                label.grid(row=row, column=column, sticky="ew", padx=1, pady=1)
                labels.append(label)
            self.operation_reference_rows[code] = labels

        flags_panel = ctk.CTkFrame(
            reference,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
        )
        flags_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(5, 6),
            pady=6,
        )
        flags_panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            flags_panel,
            text="Legenda das flags da ULA",
            text_color=TEXT,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=16,
            pady=(14, 5),
        )
        ctk.CTkLabel(
            flags_panel,
            text="Cada flag descreve uma condição produzida pela última operação.",
            text_color=MUTED,
            wraplength=390,
            justify="left",
            font=ctk.CTkFont(size=12),
        ).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            padx=16,
            pady=(0, 10),
        )

        flag_descriptions = (
            ("Z", "Zero", "O resultado da ULA é igual a zero."),
            (
                "C",
                "Vai-um / Empréstimo",
                "Indica vai-um na soma ou empréstimo na subtração.",
            ),
            ("N", "Negativo", "O bit mais significativo do resultado está ligado."),
            (
                "V",
                "Estouro aritmético",
                "A multiplicação ultrapassou a capacidade de 4 bits.",
            ),
            ("D", "Divisão por zero", "A operação de divisão recebeu B igual a zero."),
        )
        for row, (flag, title, description) in enumerate(
            flag_descriptions,
            start=2,
        ):
            badge_color = RED if flag in {"V", "D"} else CYAN
            ctk.CTkLabel(
                flags_panel,
                text=flag,
                width=42,
                height=42,
                corner_radius=6,
                fg_color=badge_color,
                text_color="#031014",
                font=ctk.CTkFont(size=17, weight="bold"),
            ).grid(row=row, column=0, padx=(16, 10), pady=5)
            ctk.CTkLabel(
                flags_panel,
                text=f"{title}\n{description}",
                text_color=TEXT,
                justify="left",
                anchor="w",
                wraplength=340,
                font=ctk.CTkFont(size=12),
            ).grid(row=row, column=1, sticky="ew", padx=(0, 14), pady=5)

        history_panel = ctk.CTkFrame(
            self.overview_scroll,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
        )
        history_panel.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=6,
            pady=(6, 12),
        )
        history_panel.grid_columnconfigure(0, weight=1)

        history_header = ctk.CTkFrame(
            history_panel,
            fg_color="transparent",
            corner_radius=0,
        )
        history_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 7))
        history_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            history_header,
            text="Operações recentes gravadas na EEPROM",
            text_color=TEXT,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            history_header,
            textvariable=self.history_status_var,
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ctk.CTkButton(
            history_header,
            text="Atualizar histórico",
            command=self._request_static,
            width=138,
            height=32,
            fg_color=BLUE,
            hover_color="#3D66CE",
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        history_table = ctk.CTkFrame(
            history_panel,
            fg_color="#09171B",
            corner_radius=6,
        )
        history_table.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))
        column_weights = (1, 2, 2, 2, 4, 2, 3)
        for column, weight in enumerate(column_weights):
            history_table.grid_columnconfigure(column, weight=weight)

        history_headers = (
            "Registro",
            "A",
            "B",
            "Código",
            "Operação",
            "Resultado",
            "Flags",
        )
        for column, text in enumerate(history_headers):
            ctk.CTkLabel(
                history_table,
                text=text,
                height=31,
                fg_color="#18343C",
                text_color=CYAN,
                font=ctk.CTkFont(size=11, weight="bold"),
            ).grid(row=0, column=column, sticky="ew", padx=1, pady=1)

        history_keys = (
            "index",
            "a",
            "b",
            "code",
            "operation",
            "result",
            "flags",
        )
        for row in range(10):
            row_widgets: dict[str, ctk.CTkLabel] = {}
            background = "#0A181D" if row % 2 == 0 else "#10242A"
            for column, key in enumerate(history_keys):
                label = ctk.CTkLabel(
                    history_table,
                    text="—",
                    height=30,
                    fg_color=background,
                    text_color=MUTED,
                    font=(
                        ctk.CTkFont(family="Consolas", size=11)
                        if key != "operation"
                        else ctk.CTkFont(size=11)
                    ),
                )
                label.grid(
                    row=row + 1,
                    column=column,
                    sticky="ew",
                    padx=1,
                    pady=1,
                )
                row_widgets[key] = label
            self.history_rows.append(row_widgets)

    def _build_ports_tab(self) -> None:
        tab = self.ports_tab
        tab.grid_columnconfigure((0, 1, 2), weight=1, uniform="ports")
        tab.grid_rowconfigure(0, weight=1)

        for column, port_name in enumerate(("B", "C", "D")):
            section = ctk.CTkFrame(
                tab,
                fg_color=SURFACE,
                border_color=BORDER,
                border_width=1,
            )
            section.grid(row=0, column=column, sticky="nsew", padx=7, pady=12)
            section.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                section,
                text=f"PORT {port_name}",
                text_color=TEXT,
                font=ctk.CTkFont(size=18, weight="bold"),
            ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 9))

            widgets: dict[str, ByteRegisterWidget] = {}
            for row, register in enumerate(("DDR", "PORT", "PIN"), start=1):
                widget = ByteRegisterWidget(section, f"{register}{port_name}")
                widget.grid(row=row, column=0, sticky="ew", padx=12, pady=7)
                widgets[register.lower()] = widget
            self.port_widgets[port_name] = widgets

    def _build_timers_tab(self) -> None:
        tab = self.timers_tab
        tab.grid_columnconfigure((0, 1, 2), weight=1, uniform="timers")
        tab.grid_rowconfigure(0, weight=1)

        timer_specs = {
            "Temporizador 0": ("tcnt0", "tccr0a", "tccr0b"),
            "Temporizador 1": ("tcnt1", "tccr1a", "tccr1b"),
            "Temporizador 2": ("tcnt2", "tccr2a", "tccr2b"),
        }
        for column, (title, keys) in enumerate(timer_specs.items()):
            section = ctk.CTkFrame(
                tab,
                fg_color=SURFACE,
                border_color=BORDER,
                border_width=1,
            )
            section.grid(row=0, column=column, sticky="nsew", padx=7, pady=12)
            section.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                section,
                text=title,
                text_color=TEXT,
                font=ctk.CTkFont(size=18, weight="bold"),
            ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 10))

            for row, key in enumerate(keys, start=1):
                metric = MetricWidget(section, key.upper())
                metric.grid(row=row, column=0, sticky="ew", padx=12, pady=7)
                self.timer_metrics[key] = metric

        ctk.CTkLabel(
            tab,
            text=(
                "Os registradores são apenas observados; o painel não altera "
                "a configuração dos temporizadores."
            ),
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, columnspan=3, pady=(0, 10))

    def _build_memory_tab(self) -> None:
        tab = self.memory_tab
        tab.grid_columnconfigure(0, weight=5)
        tab.grid_columnconfigure(1, weight=3)
        tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(tab, fg_color=SURFACE, border_color=BORDER, border_width=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left.grid_columnconfigure(0, weight=1)

        memory_header = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0)
        memory_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(13, 8))
        memory_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            memory_header,
            text="Mapa de calor da SRAM monitorada",
            text_color=TEXT,
            font=ctk.CTkFont(size=19, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        monitored_percent = SRAM_SIZE / ATMEGA328P_SRAM_SIZE * 100
        total_sram_text = f"{ATMEGA328P_SRAM_SIZE:,}".replace(",", ".")
        monitored_percent_text = f"{monitored_percent:.2f}".replace(".", ",")
        ctk.CTkLabel(
            memory_header,
            text=(
                f"SRAM total do ATmega328P: {total_sram_text} bytes  |  "
                f"Janela instrumentada: {SRAM_SIZE} bytes "
                f"({monitored_percent_text}%)"
            ),
            text_color=CYAN,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ctk.CTkLabel(
            memory_header,
            text=(
                "Cada célula representa um byte real de ula_probe[128]. "
                "A cor indica o valor armazenado, de 0x00 até 0xFF."
            ),
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
        ).grid(row=2, column=0, sticky="w", pady=(3, 0))

        self.heatmap = MemoryHeatmap(left, on_select=self._inspect_sram)
        self.heatmap.grid(row=1, column=0, padx=14, pady=(0, 7))

        color_legend = ctk.CTkFrame(left, fg_color="transparent", corner_radius=0)
        color_legend.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        legend_items = (
            ("Valor baixo", "#0C1E37", TEXT),
            ("Valor médio", "#007791", TEXT),
            ("Valor alto", "#3EF5BE", "#031014"),
            ("Alterado agora", AMBER, "#1A1200"),
            ("Selecionado", "#F5F7FA", "#031014"),
        )
        for column, (text, color, text_color) in enumerate(legend_items):
            color_legend.grid_columnconfigure(column, weight=1, uniform="memory_legend")
            ctk.CTkLabel(
                color_legend,
                text=text,
                height=28,
                corner_radius=5,
                fg_color=color,
                text_color=text_color,
                font=ctk.CTkFont(size=10, weight="bold"),
            ).grid(row=0, column=column, sticky="ew", padx=3)

        inspector = ctk.CTkFrame(
            left,
            fg_color=SURFACE_ALT,
            border_color=CYAN,
            border_width=2,
            corner_radius=8,
        )
        inspector.grid(row=3, column=0, sticky="ew", padx=16, pady=(2, 16))
        inspector.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            inspector,
            text="Inspetor de endereço",
            text_color=CYAN,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(12, 2))
        ctk.CTkLabel(
            inspector,
            textvariable=self.inspector_title_var,
            text_color=TEXT,
            font=ctk.CTkFont(size=17, weight="bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 5))
        self.inspector_label = ctk.CTkLabel(
            inspector,
            textvariable=self.inspector_var,
            height=112,
            text_color=TEXT,
            justify="left",
            anchor="nw",
            wraplength=690,
            font=ctk.CTkFont(size=12),
        )
        self.inspector_label.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=15,
            pady=(0, 13),
        )

        right = ctk.CTkFrame(tab, fg_color=SURFACE, border_color=BORDER, border_width=1)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(right, fg_color="transparent", corner_radius=0)
        toolbar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        toolbar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            toolbar,
            text="EEPROM e memória FLASH",
            text_color=TEXT,
            font=ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            toolbar,
            text="Atualizar memórias",
            command=self._request_static,
            width=142,
            height=32,
            fg_color=BLUE,
            hover_color="#3D66CE",
        ).grid(row=0, column=1, sticky="e")

        static_tabs = ctk.CTkTabview(
            right,
            fg_color=SURFACE,
            segmented_button_fg_color=OFF,
            segmented_button_selected_color=CYAN,
            segmented_button_selected_hover_color="#00B8D9",
            segmented_button_unselected_color=SURFACE_ALT,
            segmented_button_unselected_hover_color="#314A54",
            text_color=TEXT,
        )
        static_tabs.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        eeprom_tab = static_tabs.add("EEPROM")
        flash_tab = static_tabs.add("FLASH")

        for memory_tab in (eeprom_tab, flash_tab):
            memory_tab.configure(fg_color=SURFACE)
            memory_tab.grid_columnconfigure(0, weight=1)
            memory_tab.grid_rowconfigure(0, weight=1)

        self.eeprom_text = self._memory_textbox(eeprom_tab)
        self.flash_text = self._memory_textbox(flash_tab)
        self._set_text(
            self.eeprom_text,
            "Aguardando a leitura da EEPROM.\n"
            "Use o botão “Atualizar memórias” para solicitar uma nova cópia.",
        )
        self._set_text(
            self.flash_text,
            "A memória FLASH contém o programa gravado no microcontrolador.\n"
            "Ela é somente leitura durante a execução e normalmente não muda.",
        )

    def _memory_textbox(self, parent: ctk.CTkFrame) -> ctk.CTkTextbox:
        textbox = ctk.CTkTextbox(
            parent,
            fg_color="#09171B",
            border_color=BORDER,
            border_width=1,
            text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="none",
        )
        textbox.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        return textbox

    def _toggle_connection(self) -> None:
        if self.connection_state in {"connecting", "connected"}:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        self._disconnect_source()
        try:
            baud = int(self.baud_var.get().strip())
            if baud <= 0:
                raise ValueError
        except ValueError:
            self._set_status("Taxa de transmissão inválida.", "error")
            return

        if self.simulate_var.get():
            self.source = SimulatorWorker(self.events)
        else:
            selected_port = self.port_var.get().strip()
            port = (
                None
                if selected_port in {"", "Automática"}
                else selected_port
            )
            self.source = SerialWorker(self.events, port=port, baud=baud)

        self.connection_state = "connecting"
        self._refresh_connection_controls()
        self.source.start()

    def _disconnect(self) -> None:
        self._disconnect_source()
        self.connection_state = "disconnected"
        self._set_status("Desconectado.", "offline")
        self.device_var.set("Aguardando dispositivo")
        self._refresh_connection_controls()

    def _disconnect_source(self) -> None:
        if self.source is not None:
            self.source.stop()
        self.source = None

    def _request_static(self) -> None:
        if self.source is None:
            self._set_status(
                "Conecte o dispositivo antes de atualizar EEPROM e FLASH.",
                "error",
            )
            return
        self.source.request_static()
        self._set_status(
            "Solicitação de EEPROM e FLASH enviada.",
            "connected",
        )

    def _refresh_ports(self) -> None:
        available = list_serial_ports()
        values = ["Automática", *(device for device, _ in available)]
        current = self.port_var.get()
        if self.initial_port and self.initial_port not in values:
            values.append(self.initial_port)
        self.port_combo.configure(values=values)
        if current not in values:
            self.port_var.set("Automática")

    def _poll_events(self) -> None:
        for _ in range(200):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)
        self.after(50, self._poll_events)

    def _handle_event(self, event: SourceEvent) -> None:
        if event.kind == "status":
            self.connection_state = str(event.data)
            if event.data == "connected":
                self._set_status(event.message, "connected")
            elif event.data == "connecting":
                self._set_status(event.message, "connecting")
            elif self.source is None or not self.source.running:
                self._set_status(event.message, "offline")
            self._refresh_connection_controls()
            return

        if event.kind in {"error", "protocol_error"}:
            self._set_status(event.message, "error")
            if event.kind == "error":
                self.connection_state = "disconnected"
                self._refresh_connection_controls()
            return

        if event.kind == "frame":
            frame = event.data
            if isinstance(frame, HelloFrame):
                self.device_var.set(
                    f"{frame.device} | Firmware {frame.firmware} | "
                    f"{frame.sample_hz} amostras/s"
                )
            elif isinstance(frame, SnapshotFrame):
                self.latest_snapshot = frame
                self._render_snapshot(frame)
            elif isinstance(frame, MemoryFrame):
                self.latest_memory = frame
                self._render_memory(frame)

    def _render_snapshot(self, frame: SnapshotFrame) -> None:
        ula = frame.ula
        self.sequence_var.set(f"amostra {frame.sequence}")
        elapsed = f"{frame.millis / 1000:,.1f}".replace(",", "X").replace(
            ".", ","
        ).replace("X", ".")
        self.uptime_var.set(f"tempo {elapsed}s")

        self.ula_metrics["a"].set(f"{ula.a:02d} / {ula.a:04b}")
        self.ula_metrics["b"].set(f"{ula.b:02d} / {ula.b:04b}")
        self.ula_metrics["operation"].set(
            f"{ula.operation} {ula.operation_name}"
        )
        self.ula_metrics["result"].set(f"{ula.result:02d} / {ula.result:04b}")
        self.ula_metrics["input"].set(
            f"{ula.input_value:02d} / {ula.input_value:04b}"
        )
        self.ula_metrics["stage"].set(ula.stage_name)
        self._highlight_operation_reference(ula.operation)

        flag_map = {
            "Z": bool(ula.flags & FLAG_ZERO),
            "C": bool(ula.flags & FLAG_CARRY),
            "N": bool(ula.flags & FLAG_NEGATIVE),
            "V": bool(ula.flags & FLAG_OVERFLOW),
            "D": bool(ula.flags & FLAG_DIV_ZERO),
        }
        for name, active in flag_map.items():
            warning = name in {"V", "D"} and active
            self.ula_flags[name].configure(
                text=f"{name}\n{int(active)}",
                fg_color=RED if warning else CYAN if active else OFF,
                text_color="#031014" if active else MUTED,
            )

        self.sreg_register.set_value(frame.sreg)
        for name, bit in zip(
            ("I", "T", "H", "S", "V", "N", "Z", "C"),
            range(7, -1, -1),
        ):
            active = bool(frame.sreg & (1 << bit))
            self.sreg_flags[name].configure(
                text=f"{name}\n{int(active)}",
                fg_color=CYAN if active else OFF,
                text_color="#031014" if active else MUTED,
            )

        self._render_ports(frame)

        for key, metric in self.timer_metrics.items():
            value = getattr(frame.timers, key)
            width = 4 if key == "tcnt1" else 2
            metric.set(f"{value} / 0x{value:0{width}X}")

        self.adc_raw.set(f"{frame.adc.a0} / 1023")
        voltage_text = f"{frame.adc.volts:.3f}".replace(".", ",")
        self.adc_voltage.set(f"{voltage_text} V")
        self.adc_bar.set(frame.adc.a0 / 1023)
        self._render_memory_heatmap(frame)

    def _render_ports(self, frame: SnapshotFrame) -> None:
        if self.tabview.get() != "Portas":
            return

        now = time.monotonic()
        if now - self._last_ports_render_at < self._ports_render_interval:
            return
        self._last_ports_render_at = now

        for port_name, state in frame.ports.items():
            widgets = self.port_widgets.get(port_name)
            if widgets is None:
                continue
            widgets["ddr"].set_value(state.ddr)
            widgets["port"].set_value(state.port)
            widgets["pin"].set_value(state.pin)

    def _render_memory_heatmap(self, frame: SnapshotFrame) -> None:
        if self.tabview.get() != "Memória":
            return

        now = time.monotonic()
        if now - self._last_memory_render_at < self._memory_render_interval:
            return
        self._last_memory_render_at = now

        self.heatmap.update_bytes(frame.sram)
        selected_index = self.heatmap.selected_index
        self._inspect_sram(selected_index, frame.sram[selected_index])

    def _highlight_operation_reference(self, operation: int) -> None:
        if operation == self._highlighted_operation:
            return
        self._highlighted_operation = operation

        for code, labels in self.operation_reference_rows.items():
            active = code == operation
            normal_background = "#0A181D" if code % 2 == 0 else "#10242A"
            background = "#0B5967" if active else normal_background
            for column, label in enumerate(labels):
                label.configure(
                    fg_color=background,
                    text_color=(
                        "#FFFFFF"
                        if active
                        else CYAN if column == 1 else TEXT
                    ),
                )

    def _render_memory(self, frame: MemoryFrame) -> None:
        self._set_text(
            self.eeprom_text,
            "EEPROM do ATmega328P — cópia dos primeiros "
            f"{len(frame.eeprom)} bytes\n"
            "Os quatro primeiros bytes formam o cabeçalho do histórico da ULA.\n\n"
            + self._hex_dump(frame.eeprom),
        )
        self._set_text(
            self.flash_text,
            "Memória FLASH de programa — somente leitura durante a execução\n"
            "Esta é uma janela de diagnóstico; o conteúdo normalmente permanece "
            "estável enquanto o Arduino está ligado.\n\n"
            + self._hex_dump(frame.flash),
        )

        records = decode_eeprom_history(frame.eeprom)
        self._render_history_table(records)
        self._set_status("EEPROM e FLASH atualizadas.", "connected")

    def _render_history_table(
        self,
        records: list[dict[str, int | str]],
    ) -> None:
        recent_records = list(reversed(records))[: len(self.history_rows)]
        if recent_records:
            total = len(records)
            operation_word = "operação" if total == 1 else "operações"
            saved_word = "salva" if total == 1 else "salvas"
            self.history_status_var.set(
                f"{total} {operation_word} {saved_word}; "
                "exibindo as mais recentes primeiro."
            )
        else:
            self.history_status_var.set(
                "Nenhuma operação válida foi encontrada na EEPROM."
            )

        for row_index, row_widgets in enumerate(self.history_rows):
            background = (
                "#123C45"
                if row_index == 0 and recent_records
                else "#0A181D" if row_index % 2 == 0 else "#10242A"
            )
            if row_index >= len(recent_records):
                values = {key: "—" for key in row_widgets}
                colors = {key: MUTED for key in row_widgets}
            else:
                record = recent_records[row_index]
                operation = int(record["operation"])
                values = {
                    "index": f"{int(record['index']):02d}",
                    "a": f"{int(record['a']):02d} / {int(record['a']):04b}",
                    "b": f"{int(record['b']):02d} / {int(record['b']):04b}",
                    "code": f"{operation} / {operation:03b}",
                    "operation": str(record["operation_name"]),
                    "result": (
                        f"{int(record['result']):02d} / "
                        f"{int(record['result']):04b}"
                    ),
                    "flags": self._format_ula_flags(int(record["flags"])),
                }
                colors = {
                    key: CYAN if key in {"code", "flags"} else TEXT
                    for key in row_widgets
                }

            for key, label in row_widgets.items():
                label.configure(
                    text=values[key],
                    fg_color=background,
                    text_color=colors[key],
                )

    def _inspect_sram(self, index: int, value: int) -> None:
        meaning = sram_meaning(index)
        description = sram_description(index)
        adc_note = ""
        if index in {14, 15} and self.latest_snapshot is not None:
            adc = self.latest_snapshot.adc
            voltage_text = f"{adc.volts:.3f}".replace(".", ",")
            adc_note = (
                f"\n\nLeitura ADC completa neste instante: {adc.a0} de 1023 "
                f"({voltage_text} V)."
            )

        self.inspector_title_var.set(f"ula_probe[{index}] — {meaning}")
        self.inspector_var.set(
            f"Deslocamento na janela: 0x{index:02X}\n"
            f"Valor: {value} decimal  |  0x{value:02X} hexadecimal  |  "
            f"{value:08b} binário\n\n"
            f"O que representa:\n{description}{adc_note}"
        )

    @staticmethod
    def _format_ula_flags(flags: int) -> str:
        names = (
            ("Z", FLAG_ZERO),
            ("C", FLAG_CARRY),
            ("N", FLAG_NEGATIVE),
            ("V", FLAG_OVERFLOW),
            ("D", FLAG_DIV_ZERO),
        )
        active = [name for name, mask in names if flags & mask]
        return ", ".join(active) if active else "Nenhuma"

    def _refresh_connection_controls(self) -> None:
        connected = self.connection_state in {"connecting", "connected"}
        self.connect_button.configure(
            text="Desconectar" if connected else "Conectar",
            fg_color=RED if connected else GREEN,
            hover_color="#D33D59" if connected else "#2FC765",
            text_color=TEXT if connected else "#04120A",
        )

    def _set_status(self, message: str, state: str) -> None:
        self.status_var.set(message)
        styles = {
            "connected": (GREEN, "#04120A", "CONECTADO"),
            "connecting": (AMBER, "#1A1200", "CONECTANDO"),
            "error": (RED, TEXT, "ERRO"),
            "offline": (OFF, MUTED, "DESCONECTADO"),
        }
        background, foreground, text = styles.get(state, styles["offline"])
        self.status_badge.configure(
            text=text,
            fg_color=background,
            text_color=foreground,
        )

    @staticmethod
    def _hex_dump(data: bytes, width: int = 16) -> str:
        lines = []
        for offset in range(0, len(data), width):
            chunk = data[offset : offset + width]
            hex_part = " ".join(f"{value:02X}" for value in chunk)
            binary = " ".join(f"{value:08b}" for value in chunk[:4])
            lines.append(f"{offset:04X}: {hex_part:<47}  {binary}")
        return "\n".join(lines)

    @staticmethod
    def _set_text(textbox: ctk.CTkTextbox, text: str) -> None:
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")

    def _on_close(self) -> None:
        self._disconnect_source()
        self.destroy()


def run_gui(
    initial_port: str | None = None,
    baud: int = 115200,
    simulate: bool = False,
) -> None:
    app = AvrXrayApp(
        initial_port=initial_port,
        baud=baud,
        simulate=simulate,
    )
    app.mainloop()
