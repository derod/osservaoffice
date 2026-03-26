"""
Lightweight i18n helper for OSSERVA OFFICE UI labels.

Usage in templates:  {{ _('Dashboard') }}
The function reads g.user["language"] (defaults to "en") and returns
the translated string, falling back to the English key when no
translation exists.
"""

from flask import g

# ---------------------------------------------------------------------------
# Translation dictionaries – keyed by English label
# ---------------------------------------------------------------------------
_TRANSLATIONS = {
    # ── Sidebar / nav ──────────────────────────────────────────────────
    "Dashboard": {
        "es": "Panel",
        "it": "Pannello",
        "ja": "ダッシュボード",
        "pt": "Painel",
    },
    "Cases": {
        "es": "Casos",
        "it": "Casi",
        "ja": "案件",
        "pt": "Casos",
    },
    "Calendar": {
        "es": "Calendario",
        "it": "Calendario",
        "ja": "カレンダー",
        "pt": "Calendário",
    },
    "Availability": {
        "es": "Disponibilidad",
        "it": "Disponibilità",
        "ja": "空き状況",
        "pt": "Disponibilidade",
    },
    "Employees": {
        "es": "Empleados",
        "it": "Dipendenti",
        "ja": "従業員",
        "pt": "Funcionários",
    },
    "Schedule Requests": {
        "es": "Solicitudes",
        "it": "Richieste ferie",
        "ja": "スケジュール申請",
        "pt": "Solicitações",
    },
    "Documents": {
        "es": "Documentos",
        "it": "Documenti",
        "ja": "書類",
        "pt": "Documentos",
    },
    "Clients": {
        "es": "Clientes",
        "it": "Clienti",
        "ja": "クライアント",
        "pt": "Clientes",
    },
    "Announcements": {
        "es": "Anuncios",
        "it": "Annunci",
        "ja": "お知らせ",
        "pt": "Avisos",
    },
    "Clock In": {
        "es": "Registrar entrada",
        "it": "Timbra entrata",
        "ja": "出勤打刻",
        "pt": "Registrar entrada",
    },
    "Log In": {
        "es": "Registro de accesos",
        "it": "Registro accessi",
        "ja": "ログイン履歴",
        "pt": "Registro de acessos",
    },
    "Finances": {
        "es": "Finanzas",
        "it": "Finanze",
        "ja": "財務",
        "pt": "Finanças",
    },
    "Settings": {
        "es": "Configuración",
        "it": "Impostazioni",
        "ja": "設定",
        "pt": "Configurações",
    },
    "Logout": {
        "es": "Cerrar sesión",
        "it": "Esci",
        "ja": "ログアウト",
        "pt": "Sair",
    },
    "Work": {
        "es": "Trabajo",
        "it": "Lavoro",
        "ja": "業務",
        "pt": "Trabalho",
    },
    "Schedule": {
        "es": "Agenda",
        "it": "Agenda",
        "ja": "スケジュール",
        "pt": "Agenda",
    },
    "Management": {
        "es": "Gestión",
        "it": "Gestione",
        "ja": "管理",
        "pt": "Gestão",
    },
    "Admin": {
        "es": "Administración",
        "it": "Amministrazione",
        "ja": "管理者",
        "pt": "Administração",
    },

    # ── Topbar ─────────────────────────────────────────────────────────
    "Search cases, clients, employees...": {
        "es": "Buscar casos, clientes, empleados...",
        "it": "Cerca casi, clienti, dipendenti...",
        "ja": "案件・クライアント・従業員を検索...",
        "pt": "Buscar casos, clientes, funcionários...",
    },
    "Toggle theme": {
        "es": "Cambiar tema",
        "it": "Cambia tema",
        "ja": "テーマ切替",
        "pt": "Alternar tema",
    },

    # ── Dashboard stats ────────────────────────────────────────────────
    "Active Cases": {
        "es": "Casos activos",
        "it": "Casi attivi",
        "ja": "進行中の案件",
        "pt": "Casos ativos",
    },
    "Due in 7 Days": {
        "es": "Vencen en 7 días",
        "it": "Scadenza 7 giorni",
        "ja": "7日以内に期限",
        "pt": "Vencem em 7 dias",
    },
    "Due in 30 Days": {
        "es": "Vencen en 30 días",
        "it": "Scadenza 30 giorni",
        "ja": "30日以内に期限",
        "pt": "Vencem em 30 dias",
    },
    "Tasks Today": {
        "es": "Tareas hoy",
        "it": "Attività oggi",
        "ja": "今日のタスク",
        "pt": "Tarefas hoje",
    },
    "Appointments Today": {
        "es": "Citas hoy",
        "it": "Appuntamenti oggi",
        "ja": "今日の予定",
        "pt": "Compromissos hoje",
    },
    "Pending Requests": {
        "es": "Solicitudes pendientes",
        "it": "Richieste in attesa",
        "ja": "保留中の申請",
        "pt": "Solicitações pendentes",
    },
    "Team Available": {
        "es": "Equipo disponible",
        "it": "Team disponibile",
        "ja": "対応可能なメンバー",
        "pt": "Equipe disponível",
    },
    "Team Overview": {
        "es": "Equipo",
        "it": "Panoramica team",
        "ja": "チーム概要",
        "pt": "Visão da equipe",
    },
    "View all →": {
        "es": "Ver todo →",
        "it": "Vedi tutti →",
        "ja": "すべて表示 →",
        "pt": "Ver todos →",
    },
    "View agenda": {
        "es": "Ver agenda",
        "it": "Vedi agenda",
        "ja": "予定を見る",
        "pt": "Ver agenda",
    },
    "Request change": {
        "es": "Solicitar cambio",
        "it": "Richiedi modifica",
        "ja": "変更を申請",
        "pt": "Solicitar alteração",
    },
    "No team members": {
        "es": "Sin miembros del equipo",
        "it": "Nessun membro del team",
        "ja": "メンバーがいません",
        "pt": "Sem membros na equipe",
    },
    "Next up": {
        "es": "Siguiente",
        "it": "Prossimo",
        "ja": "次の予定",
        "pt": "Próximo",
    },
    "No upcoming appointments today": {
        "es": "Sin citas programadas hoy",
        "it": "Nessun appuntamento oggi",
        "ja": "今日の予定はありません",
        "pt": "Sem compromissos hoje",
    },
    "No pending requests": {
        "es": "Sin solicitudes pendientes",
        "it": "Nessuna richiesta in attesa",
        "ja": "保留中の申請はありません",
        "pt": "Sem solicitações pendentes",
    },
    "Quick Actions": {
        "es": "Acciones rápidas",
        "it": "Azioni rapide",
        "ja": "クイックアクション",
        "pt": "Ações rápidas",
    },
    "New Case": {
        "es": "Nuevo caso",
        "it": "Nuovo caso",
        "ja": "新規案件",
        "pt": "Novo caso",
    },
    "New Appointment": {
        "es": "Nueva cita",
        "it": "Nuovo appuntamento",
        "ja": "新規予定",
        "pt": "Novo compromisso",
    },
    "New Client": {
        "es": "Nuevo cliente",
        "it": "Nuovo cliente",
        "ja": "新規クライアント",
        "pt": "Novo cliente",
    },
    "Approve": {
        "es": "Aprobar",
        "it": "Approva",
        "ja": "承認",
        "pt": "Aprovar",
    },
    "Deny": {
        "es": "Rechazar",
        "it": "Rifiuta",
        "ja": "却下",
        "pt": "Recusar",
    },
    "Pending": {
        "es": "Pendiente",
        "it": "In attesa",
        "ja": "保留中",
        "pt": "Pendente",
    },

    # ── Agenda / Employee page ─────────────────────────────────────────
    "Today's Schedule": {
        "es": "Agenda de hoy",
        "it": "Programma di oggi",
        "ja": "今日のスケジュール",
        "pt": "Agenda de hoje",
    },
    "No appointments today": {
        "es": "Sin citas hoy",
        "it": "Nessun appuntamento oggi",
        "ja": "今日の予定はありません",
        "pt": "Sem compromissos hoje",
    },
    "Priority Cases": {
        "es": "Casos prioritarios",
        "it": "Casi prioritari",
        "ja": "優先案件",
        "pt": "Casos prioritários",
    },
    "No active cases assigned": {
        "es": "Sin casos activos asignados",
        "it": "Nessun caso attivo assegnato",
        "ja": "割り当てられた進行中の案件はありません",
        "pt": "Sem casos ativos atribuídos",
    },
    "Case Health": {
        "es": "Estado de los casos",
        "it": "Stato dei casi",
        "ja": "案件の状態",
        "pt": "Saúde dos casos",
    },
    "Upcoming Agenda": {
        "es": "Agenda próxima",
        "it": "Prossimi impegni",
        "ja": "今後の予定",
        "pt": "Agenda futura",
    },
    "— next 7 days": {
        "es": "— próximos 7 días",
        "it": "— prossimi 7 giorni",
        "ja": "— 今後7日間",
        "pt": "— próximos 7 dias",
    },
    "No appointments in the next 7 days": {
        "es": "Sin citas en los próximos 7 días",
        "it": "Nessun appuntamento nei prossimi 7 giorni",
        "ja": "今後7日間に予定はありません",
        "pt": "Sem compromissos nos próximos 7 dias",
    },
    "Office Check-In": {
        "es": "Registro de oficina",
        "it": "Check-in ufficio",
        "ja": "オフィス出勤",
        "pt": "Check-in do escritório",
    },
    "Clocked in at": {
        "es": "Entrada a las",
        "it": "Entrata alle",
        "ja": "出勤時刻",
        "pt": "Entrada às",
    },
    "Clocked out at": {
        "es": "Salida a las",
        "it": "Uscita alle",
        "ja": "退勤時刻",
        "pt": "Saída às",
    },
    "Re-record": {
        "es": "Re-registrar",
        "it": "Ri-registra",
        "ja": "再記録",
        "pt": "Registrar novamente",
    },
    "Clock Out": {
        "es": "Registrar salida",
        "it": "Timbra uscita",
        "ja": "退勤打刻",
        "pt": "Registrar saída",
    },
    "Recording as admin on behalf of": {
        "es": "Registrando como admin en nombre de",
        "it": "Registrazione come admin per conto di",
        "ja": "管理者として代理記録中：",
        "pt": "Registrando como admin em nome de",
    },
    "On Time": {
        "es": "A tiempo",
        "it": "In orario",
        "ja": "定時",
        "pt": "No horário",
    },
    "Late": {
        "es": "Tarde",
        "it": "In ritardo",
        "ja": "遅刻",
        "pt": "Atrasado",
    },
    "Exception": {
        "es": "Excepción",
        "it": "Eccezione",
        "ja": "例外",
        "pt": "Exceção",
    },
    "Optional note (e.g. working remotely)...": {
        "es": "Nota opcional (ej. teletrabajo)...",
        "it": "Nota opzionale (es. lavoro da remoto)...",
        "ja": "メモ（例：リモートワーク）...",
        "pt": "Nota opcional (ex. trabalho remoto)...",
    },
    "No case (general check-in)": {
        "es": "Sin caso (registro general)",
        "it": "Nessun caso (check-in generico)",
        "ja": "案件なし（一般出勤）",
        "pt": "Sem caso (check-in geral)",
    },
    "Attendance History": {
        "es": "Historial de asistencia",
        "it": "Storico presenze",
        "ja": "出勤履歴",
        "pt": "Histórico de presença",
    },
    "Today": {
        "es": "Hoy",
        "it": "Oggi",
        "ja": "今日",
        "pt": "Hoje",
    },
    "This Week": {
        "es": "Esta semana",
        "it": "Questa settimana",
        "ja": "今週",
        "pt": "Esta semana",
    },
    "7 Days": {
        "es": "7 días",
        "it": "7 giorni",
        "ja": "7日間",
        "pt": "7 dias",
    },
    "14 Days": {
        "es": "14 días",
        "it": "14 giorni",
        "ja": "14日間",
        "pt": "14 dias",
    },
    "30 Days": {
        "es": "30 días",
        "it": "30 giorni",
        "ja": "30日間",
        "pt": "30 dias",
    },
    "All": {
        "es": "Todos",
        "it": "Tutti",
        "ja": "すべて",
        "pt": "Todos",
    },
    "All cases": {
        "es": "Todos los casos",
        "it": "Tutti i casi",
        "ja": "すべての案件",
        "pt": "Todos os casos",
    },
    "No check-in entries match the selected filters.": {
        "es": "No hay registros que coincidan con los filtros.",
        "it": "Nessuna voce corrisponde ai filtri selezionati.",
        "ja": "選択したフィルターに一致する記録はありません。",
        "pt": "Nenhum registro corresponde aos filtros selecionados.",
    },
    "Delete this check-in entry?": {
        "es": "¿Eliminar este registro de entrada?",
        "it": "Eliminare questa voce di check-in?",
        "ja": "このチェックイン記録を削除しますか？",
        "pt": "Excluir este registro de entrada?",
    },
    "Finished": {
        "es": "Finalizado",
        "it": "Terminato",
        "ja": "完了",
        "pt": "Finalizado",
    },
    "Early": {
        "es": "Temprano",
        "it": "Anticipato",
        "ja": "早退",
        "pt": "Antecipado",
    },
    "Optional note (e.g. heading to court)...": {
        "es": "Nota opcional (ej. rumbo al tribunal)...",
        "it": "Nota opzionale (es. in tribunale)...",
        "ja": "メモ（例：裁判所へ移動）...",
        "pt": "Nota opcional (ex. indo ao tribunal)...",
    },

    # ── Settings page ──────────────────────────────────────────────────
    "Your Profile": {
        "es": "Tu perfil",
        "it": "Il tuo profilo",
        "ja": "プロフィール",
        "pt": "Seu perfil",
    },
    "Full Name": {
        "es": "Nombre completo",
        "it": "Nome completo",
        "ja": "氏名",
        "pt": "Nome completo",
    },
    "Job Title": {
        "es": "Cargo",
        "it": "Qualifica",
        "ja": "役職",
        "pt": "Cargo",
    },
    "Phone": {
        "es": "Teléfono",
        "it": "Telefono",
        "ja": "電話",
        "pt": "Telefone",
    },
    "New Password": {
        "es": "Nueva contraseña",
        "it": "Nuova password",
        "ja": "新しいパスワード",
        "pt": "Nova senha",
    },
    "leave blank to keep current": {
        "es": "dejar en blanco para mantener la actual",
        "it": "lasciare vuoto per mantenere l'attuale",
        "ja": "変更しない場合は空欄のまま",
        "pt": "deixe em branco para manter a atual",
    },
    "Interface Language": {
        "es": "Idioma de la interfaz",
        "it": "Lingua dell'interfaccia",
        "ja": "表示言語",
        "pt": "Idioma da interface",
    },
    "Save Profile": {
        "es": "Guardar perfil",
        "it": "Salva profilo",
        "ja": "プロフィールを保存",
        "pt": "Salvar perfil",
    },
    "User Management": {
        "es": "Gestión de usuarios",
        "it": "Gestione utenti",
        "ja": "ユーザー管理",
        "pt": "Gerenciamento de usuários",
    },
    "New User": {
        "es": "Nuevo usuario",
        "it": "Nuovo utente",
        "ja": "新規ユーザー",
        "pt": "Novo usuário",
    },
    "Name": {
        "es": "Nombre",
        "it": "Nome",
        "ja": "名前",
        "pt": "Nome",
    },
    "Email": {
        "es": "Correo",
        "it": "Email",
        "ja": "メール",
        "pt": "Email",
    },
    "Role": {
        "es": "Rol",
        "it": "Ruolo",
        "ja": "役割",
        "pt": "Função",
    },
    "Language": {
        "es": "Idioma",
        "it": "Lingua",
        "ja": "言語",
        "pt": "Idioma",
    },
    "Status": {
        "es": "Estado",
        "it": "Stato",
        "ja": "状態",
        "pt": "Status",
    },
    "Active": {
        "es": "Activo",
        "it": "Attivo",
        "ja": "有効",
        "pt": "Ativo",
    },
    "Inactive": {
        "es": "Inactivo",
        "it": "Inattivo",
        "ja": "無効",
        "pt": "Inativo",
    },
    "AI Integrations": {
        "es": "Integraciones IA",
        "it": "Integrazioni IA",
        "ja": "AI連携",
        "pt": "Integrações IA",
    },
    "Open": {
        "es": "Abierto",
        "it": "Aperto",
        "ja": "未退勤",
        "pt": "Aberto",
    },
    "Next:": {
        "es": "Siguiente:",
        "it": "Prossimo:",
        "ja": "次:",
        "pt": "Próximo:",
    },
    "Overdue": {
        "es": "Vencido",
        "it": "Scaduto",
        "ja": "期限超過",
        "pt": "Atrasado",
    },
    "— Overdue": {
        "es": "— Vencido",
        "it": "— Scaduto",
        "ja": "— 期限超過",
        "pt": "— Atrasado",
    },
    "overdue": {
        "es": "vencidas",
        "it": "scadute",
        "ja": "期限超過",
        "pt": "atrasadas",
    },
    "due within 48h": {
        "es": "vencen en 48h",
        "it": "scadenza entro 48h",
        "ja": "48時間以内に期限",
        "pt": "vencem em 48h",
    },
    "Next deadline:": {
        "es": "Próximo vencimiento:",
        "it": "Prossima scadenza:",
        "ja": "次の期限:",
        "pt": "Próximo prazo:",
    },
    "Next task due:": {
        "es": "Próxima tarea:",
        "it": "Prossima attività:",
        "ja": "次のタスク期限:",
        "pt": "Próxima tarefa:",
    },
    "Click again to confirm": {
        "es": "Haz clic de nuevo para confirmar",
        "it": "Clicca di nuovo per confermare",
        "ja": "もう一度クリックして確認",
        "pt": "Clique novamente para confirmar",
    },
    "Recording...": {
        "es": "Registrando...",
        "it": "Registrazione...",
        "ja": "記録中...",
        "pt": "Registrando...",
    },
    "Click again within 3 seconds to confirm.": {
        "es": "Haz clic de nuevo en 3 segundos para confirmar.",
        "it": "Clicca di nuovo entro 3 secondi per confermare.",
        "ja": "3秒以内にもう一度クリックして確認してください。",
        "pt": "Clique novamente em 3 segundos para confirmar.",
    },
    "open task": {
        "es": "tarea abierta",
        "it": "attività aperta",
        "ja": "未完了タスク",
        "pt": "tarefa aberta",
    },
    "open tasks": {
        "es": "tareas abiertas",
        "it": "attività aperte",
        "ja": "未完了タスク",
        "pt": "tarefas abertas",
    },
    # ── Inbox ───────────────────────────────────────────────────────
    "Inbox": {
        "es": "Bandeja de entrada",
        "it": "Posta in arrivo",
        "ja": "受信箱",
        "pt": "Caixa de entrada",
    },
    "Compose": {
        "es": "Redactar",
        "it": "Scrivi",
        "ja": "作成",
        "pt": "Escrever",
    },
    "Received": {
        "es": "Recibidos",
        "it": "Ricevuti",
        "ja": "受信",
        "pt": "Recebidos",
    },
    "Sent": {
        "es": "Enviados",
        "it": "Inviati",
        "ja": "送信済み",
        "pt": "Enviados",
    },
    "New Message": {
        "es": "Nuevo mensaje",
        "it": "Nuovo messaggio",
        "ja": "新しいメッセージ",
        "pt": "Nova mensagem",
    },
    "To": {
        "es": "Para",
        "it": "A",
        "ja": "宛先",
        "pt": "Para",
    },
    "Subject": {
        "es": "Asunto",
        "it": "Oggetto",
        "ja": "件名",
        "pt": "Assunto",
    },
    "Message": {
        "es": "Mensaje",
        "it": "Messaggio",
        "ja": "メッセージ",
        "pt": "Mensagem",
    },
    "Send": {
        "es": "Enviar",
        "it": "Invia",
        "ja": "送信",
        "pt": "Enviar",
    },
    "Send Reply": {
        "es": "Enviar respuesta",
        "it": "Invia risposta",
        "ja": "返信を送信",
        "pt": "Enviar resposta",
    },
    "Reply": {
        "es": "Responder",
        "it": "Rispondi",
        "ja": "返信",
        "pt": "Responder",
    },
    "Back to Inbox": {
        "es": "Volver a la bandeja",
        "it": "Torna alla posta",
        "ja": "受信箱に戻る",
        "pt": "Voltar à caixa de entrada",
    },
    "Select recipient...": {
        "es": "Seleccionar destinatario...",
        "it": "Seleziona destinatario...",
        "ja": "受信者を選択...",
        "pt": "Selecionar destinatário...",
    },
    "Write your reply...": {
        "es": "Escribe tu respuesta...",
        "it": "Scrivi la tua risposta...",
        "ja": "返信を入力...",
        "pt": "Escreva sua resposta...",
    },
    "No messages yet": {
        "es": "Aún no hay mensajes",
        "it": "Nessun messaggio",
        "ja": "メッセージはありません",
        "pt": "Nenhuma mensagem ainda",
    },
    "No sent messages": {
        "es": "No hay mensajes enviados",
        "it": "Nessun messaggio inviato",
        "ja": "送信済みメッセージはありません",
        "pt": "Nenhuma mensagem enviada",
    },
    "Cancel": {
        "es": "Cancelar",
        "it": "Annulla",
        "ja": "キャンセル",
        "pt": "Cancelar",
    },
    "Trash": {
        "es": "Papelera",
        "it": "Cestino",
        "ja": "ゴミ箱",
        "pt": "Lixeira",
    },
    "Trash is empty": {
        "es": "La papelera está vacía",
        "it": "Il cestino è vuoto",
        "ja": "ゴミ箱は空です",
        "pt": "A lixeira está vazia",
    },
    "Delete": {
        "es": "Eliminar",
        "it": "Elimina",
        "ja": "削除",
        "pt": "Excluir",
    },
    "Restore": {
        "es": "Restaurar",
        "it": "Ripristina",
        "ja": "復元",
        "pt": "Restaurar",
    },
    "Delete conversation?": {
        "es": "¿Eliminar conversación?",
        "it": "Eliminare la conversazione?",
        "ja": "会話を削除しますか？",
        "pt": "Excluir conversa?",
    },
    "This will move the conversation to trash. It can be restored within 30 days.": {
        "es": "La conversación se moverá a la papelera. Se puede restaurar en 30 días.",
        "it": "La conversazione verrà spostata nel cestino. Può essere ripristinata entro 30 giorni.",
        "ja": "会話はゴミ箱に移動されます。30日以内に復元できます。",
        "pt": "A conversa será movida para a lixeira. Pode ser restaurada em 30 dias.",
    },
    "Conversation moved to trash.": {
        "es": "Conversación movida a la papelera.",
        "it": "Conversazione spostata nel cestino.",
        "ja": "会話をゴミ箱に移動しました。",
        "pt": "Conversa movida para a lixeira.",
    },
    "Conversation restored.": {
        "es": "Conversación restaurada.",
        "it": "Conversazione ripristinata.",
        "ja": "会話を復元しました。",
        "pt": "Conversa restaurada.",
    },
    "This conversation is in trash and will be permanently deleted after 30 days.": {
        "es": "Esta conversación está en la papelera y se eliminará permanentemente después de 30 días.",
        "it": "Questa conversazione è nel cestino e verrà eliminata definitivamente dopo 30 giorni.",
        "ja": "この会話はゴミ箱にあり、30日後に完全に削除されます。",
        "pt": "Esta conversa está na lixeira e será excluída permanentemente após 30 dias.",
    },
    "All fields are required.": {
        "es": "Todos los campos son obligatorios.",
        "it": "Tutti i campi sono obbligatori.",
        "ja": "すべてのフィールドが必要です。",
        "pt": "Todos os campos são obrigatórios.",
    },
    "You cannot message yourself.": {
        "es": "No puedes enviarte un mensaje a ti mismo.",
        "it": "Non puoi inviare un messaggio a te stesso.",
        "ja": "自分にメッセージを送ることはできません。",
        "pt": "Você não pode enviar uma mensagem para si mesmo.",
    },
    "Message sent.": {
        "es": "Mensaje enviado.",
        "it": "Messaggio inviato.",
        "ja": "メッセージを送信しました。",
        "pt": "Mensagem enviada.",
    },
    "Reply cannot be empty.": {
        "es": "La respuesta no puede estar vacía.",
        "it": "La risposta non può essere vuota.",
        "ja": "返信は空にできません。",
        "pt": "A resposta não pode estar vazia.",
    },

    # ── Legal Consultant ──────────────────────────────────────────────
    "Legal Consultant": {
        "es": "Consultor Legal",
        "it": "Consulente Legale",
        "ja": "法律コンサルタント",
        "pt": "Consultor Jurídico",
    },
    "OpenAI API": {
        "es": "API de OpenAI",
        "it": "API OpenAI",
        "ja": "OpenAI API",
        "pt": "API OpenAI",
    },
    "Configured": {
        "es": "Configurado",
        "it": "Configurato",
        "ja": "設定済み",
        "pt": "Configurado",
    },
    "Not configured": {
        "es": "No configurado",
        "it": "Non configurato",
        "ja": "未設定",
        "pt": "Não configurado",
    },
    "Jurisdiction": {
        "es": "Jurisdicción",
        "it": "Giurisdizione",
        "ja": "管轄",
        "pt": "Jurisdição",
    },
    "Subject Area": {
        "es": "Materia",
        "it": "Materia",
        "ja": "分野",
        "pt": "Área",
    },
    "Consultation Type": {
        "es": "Tipo de consulta",
        "it": "Tipo di consulenza",
        "ja": "相談種別",
        "pt": "Tipo de consulta",
    },
    "Sources": {
        "es": "Fuentes",
        "it": "Fonti",
        "ja": "出典",
        "pt": "Fontes",
    },
    "Confidence Level": {
        "es": "Nivel de confianza",
        "it": "Livello di affidabilità",
        "ja": "信頼度",
        "pt": "Nível de confiança",
    },
    "Mentor Mode": {
        "es": "Modo Mentor",
        "it": "Modalità Mentore",
        "ja": "メンターモード",
        "pt": "Modo Mentor",
    },
    "Active Context": {
        "es": "Contexto activo",
        "it": "Contesto attivo",
        "ja": "有効なコンテキスト",
        "pt": "Contexto ativo",
    },
    "Case Studies": {
        "es": "Casos de estudio",
        "it": "Casi di studio",
        "ja": "判例研究",
        "pt": "Estudos de caso",
    },
    "Legal Documents": {
        "es": "Documentos legales",
        "it": "Documenti legali",
        "ja": "法律文書",
        "pt": "Documentos legais",
    },
    "Active Regulations": {
        "es": "Normas activas",
        "it": "Normative vigenti",
        "ja": "現行規則",
        "pt": "Normas ativas",
    },
    "Preliminary Conclusion": {
        "es": "Conclusión preliminar",
        "it": "Conclusione preliminare",
        "ja": "暫定結論",
        "pt": "Conclusão preliminar",
    },
    "Analysis": {
        "es": "Análisis",
        "it": "Analisi",
        "ja": "分析",
        "pt": "Análise",
    },
    "Warnings": {
        "es": "Advertencias",
        "it": "Avvertenze",
        "ja": "警告",
        "pt": "Avisos",
    },
    "Suggested Next Step": {
        "es": "Siguiente paso sugerido",
        "it": "Passo successivo suggerito",
        "ja": "推奨される次のステップ",
        "pt": "Próximo passo sugerido",
    },
    "OpenAI API not configured": {
        "es": "API de OpenAI no configurada",
        "it": "API OpenAI non configurata",
        "ja": "OpenAI APIが未設定です",
        "pt": "API OpenAI não configurada",
    },
    "Used for Legal Consultant AI features": {
        "es": "Usado para funciones de IA del Consultor Legal",
        "it": "Usato per le funzionalità IA del Consulente Legale",
        "ja": "法律コンサルタントAI機能に使用",
        "pt": "Usado para funcionalidades de IA do Consultor Jurídico",
    },
    "History": {
        "es": "Historial",
        "it": "Cronologia",
        "ja": "履歴",
        "pt": "Histórico",
    },
    "No data yet": {
        "es": "Sin datos aún",
        "it": "Nessun dato ancora",
        "ja": "データなし",
        "pt": "Sem dados ainda",
    },
    "Active sources": {
        "es": "Fuentes activas",
        "it": "Fonti attive",
        "ja": "有効な出典",
        "pt": "Fontes ativas",
    },
    "View PDF": {
        "es": "Ver PDF",
        "it": "Vedi PDF",
        "ja": "PDF表示",
        "pt": "Ver PDF",
    },
    "Not evaluated": {
        "es": "No evaluado",
        "it": "Non valutato",
        "ja": "未評価",
        "pt": "Não avaliado",
    },
    "Country": {
        "es": "País",
        "it": "Paese",
        "ja": "国",
        "pt": "País",
    },
    "Documents loaded": {
        "es": "Documentos cargados",
        "it": "Documenti caricati",
        "ja": "読込済み文書",
        "pt": "Documentos carregados",
    },
    "Only use uploaded sources": {
        "es": "Solo usar fuentes cargadas",
        "it": "Usa solo fonti caricate",
        "ja": "アップロード済みソースのみ使用",
        "pt": "Usar apenas fontes carregadas",
    },
    "Include page citations": {
        "es": "Incluir citas de página",
        "it": "Includi citazioni di pagina",
        "ja": "ページ引用を含める",
        "pt": "Incluir citações de página",
    },
    "Type your legal question...": {
        "es": "Escriba su consulta legal...",
        "it": "Scrivi la tua domanda legale...",
        "ja": "法律に関する質問を入力...",
        "pt": "Digite sua pergunta jurídica...",
    },
    "New Consultation": {
        "es": "Nueva consulta",
        "it": "Nuova consulenza",
        "ja": "新規相談",
        "pt": "Nova consulta",
    },
    "Select jurisdiction...": {
        "es": "Seleccionar jurisdicción...",
        "it": "Seleziona giurisdizione...",
        "ja": "管轄を選択...",
        "pt": "Selecionar jurisdição...",
    },
    "Select subject...": {
        "es": "Seleccionar materia...",
        "it": "Seleziona materia...",
        "ja": "分野を選択...",
        "pt": "Selecionar área...",
    },
    "Select type...": {
        "es": "Seleccionar tipo...",
        "it": "Seleziona tipo...",
        "ja": "種別を選択...",
        "pt": "Selecionar tipo...",
    },
    "Labor": {
        "es": "Laboral",
        "it": "Lavoro",
        "ja": "労働",
        "pt": "Trabalhista",
    },
    "Civil": {
        "es": "Civil",
        "it": "Civile",
        "ja": "民事",
        "pt": "Civil",
    },
    "Commercial": {
        "es": "Comercial",
        "it": "Commerciale",
        "ja": "商事",
        "pt": "Comercial",
    },
    "Criminal": {
        "es": "Penal",
        "it": "Penale",
        "ja": "刑事",
        "pt": "Penal",
    },
    "Family": {
        "es": "Familia",
        "it": "Famiglia",
        "ja": "家族",
        "pt": "Família",
    },
    "Administrative": {
        "es": "Administrativo",
        "it": "Amministrativo",
        "ja": "行政",
        "pt": "Administrativo",
    },
    "General Consultation": {
        "es": "Consulta general",
        "it": "Consulenza generale",
        "ja": "一般相談",
        "pt": "Consulta geral",
    },
    "Case Analysis": {
        "es": "Análisis de caso",
        "it": "Analisi del caso",
        "ja": "事例分析",
        "pt": "Análise de caso",
    },
    "Document Review": {
        "es": "Revisión de documento",
        "it": "Revisione documenti",
        "ja": "文書レビュー",
        "pt": "Revisão de documento",
    },
    "Regulatory Check": {
        "es": "Verificación normativa",
        "it": "Verifica normativa",
        "ja": "規制確認",
        "pt": "Verificação normativa",
    },

    # ── Legal Consultant (functional chat) ─────────────────────────────
    "Legal Assistant": {
        "es": "Asistente Legal",
        "it": "Assistente Legale",
        "ja": "法律アシスタント",
        "pt": "Assistente Jurídico",
    },
    "New Conversation": {
        "es": "Nueva conversación",
        "it": "Nuova conversazione",
        "ja": "新しい会話",
        "pt": "Nova conversa",
    },
    "Recent Conversations": {
        "es": "Conversaciones recientes",
        "it": "Conversazioni recenti",
        "ja": "最近の会話",
        "pt": "Conversas recentes",
    },
    "No conversations yet": {
        "es": "Aún no hay conversaciones",
        "it": "Nessuna conversazione",
        "ja": "会話はまだありません",
        "pt": "Nenhuma conversa ainda",
    },
    "Start by asking a legal question": {
        "es": "Comienza haciendo una consulta legal",
        "it": "Inizia ponendo una domanda legale",
        "ja": "法律に関する質問から始めましょう",
        "pt": "Comece fazendo uma pergunta jurídica",
    },
    "Ask a legal question": {
        "es": "Haz una consulta legal",
        "it": "Fai una domanda legale",
        "ja": "法律に関する質問をする",
        "pt": "Faça uma pergunta jurídica",
    },
    "Ready": {
        "es": "Listo",
        "it": "Pronto",
        "ja": "準備完了",
        "pt": "Pronto",
    },
    "Current Context": {
        "es": "Contexto actual",
        "it": "Contesto attuale",
        "ja": "現在のコンテキスト",
        "pt": "Contexto atual",
    },
    "Created": {
        "es": "Creado",
        "it": "Creato",
        "ja": "作成日",
        "pt": "Criado",
    },
    "Last updated": {
        "es": "Última actualización",
        "it": "Ultimo aggiornamento",
        "ja": "最終更新",
        "pt": "Última atualização",
    },
    "Messages": {
        "es": "Mensajes",
        "it": "Messaggi",
        "ja": "メッセージ数",
        "pt": "Mensagens",
    },
    "Delete this conversation?": {
        "es": "¿Eliminar esta conversación?",
        "it": "Eliminare questa conversazione?",
        "ja": "この会話を削除しますか？",
        "pt": "Excluir esta conversa?",
    },
    "Tips": {
        "es": "Consejos",
        "it": "Suggerimenti",
        "ja": "ヒント",
        "pt": "Dicas",
    },
    "Include the country or jurisdiction": {
        "es": "Incluye el país o jurisdicción",
        "it": "Includi il paese o la giurisdizione",
        "ja": "国や管轄を含めてください",
        "pt": "Inclua o país ou jurisdição",
    },
    "Specify the subject area (labor, civil, etc.)": {
        "es": "Especifica el área (laboral, civil, etc.)",
        "it": "Specifica l'area (lavoro, civile, ecc.)",
        "ja": "分野を指定してください（労働、民事など）",
        "pt": "Especifique a área (trabalhista, civil, etc.)",
    },
    "Include relevant facts and dates": {
        "es": "Incluye hechos y fechas relevantes",
        "it": "Includi fatti e date rilevanti",
        "ja": "関連する事実と日付を含めてください",
        "pt": "Inclua fatos e datas relevantes",
    },
    "Disclaimer": {
        "es": "Aviso legal",
        "it": "Avvertenza",
        "ja": "免責事項",
        "pt": "Aviso legal",
    },
    "Informational assistance only. This does not constitute legal advice. Verify conclusions with qualified counsel.": {
        "es": "Asistencia informativa únicamente. Esto no constituye asesoría legal. Verifique las conclusiones con un profesional calificado.",
        "it": "Solo assistenza informativa. Non costituisce consulenza legale. Verificare le conclusioni con un professionista qualificato.",
        "ja": "情報提供のみを目的としています。法的助言ではありません。結論は資格のある弁護士にご確認ください。",
        "pt": "Assistência informativa apenas. Não constitui aconselhamento jurídico. Verifique as conclusões com um profissional qualificado.",
    },
}


def translate(key: str) -> str:
    """Return the translated string for the current user's language.

    Falls back to the key itself (English) when no translation is found.
    Safe to call when there is no authenticated user (returns key as-is).
    """
    try:
        user = getattr(g, "user", None)
    except RuntimeError:
        user = None
    lang = (user.get("language") if user else None) or "en"
    if lang == "en":
        return key
    entry = _TRANSLATIONS.get(key)
    if entry is None:
        return key
    return entry.get(lang, key)
