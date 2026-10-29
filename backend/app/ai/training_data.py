"""Seed training corpus (Spanish) for the document classifier.

Small on purpose: it's enough for a demonstrable MVP. In the next phase this corpus can be
replaced by real labeled documents (e.g. a CSV with columns text,label).
"""

TRAINING_SAMPLES: dict[str, list[str]] = {
    "Financiero": [
        "Factura de venta número 0045 por valor total de 2.500.000 pesos más IVA del 19%",
        "Estado de cuenta bancario del mes de marzo con saldo disponible y movimientos",
        "Balance general y estado de resultados del ejercicio contable 2025",
        "Comprobante de pago de nómina transferencia a la cuenta de ahorros",
        "Presupuesto anual de gastos e inversiones del área comercial",
        "Extracto de tarjeta de crédito con cuotas pendientes e intereses de mora",
        "Declaración de renta y retención en la fuente ante la DIAN",
        "Orden de compra a proveedor con condiciones de pago a 30 días",
        "Flujo de caja proyectado e indicadores de rentabilidad",
        "Recibo de caja por abono a la deuda del cliente",
        "Cotización de servicios con valor unitario, subtotal e impuestos",
        "Conciliación bancaria y cuentas por cobrar vencidas",
    ],
    "Legal": [
        "Contrato de prestación de servicios entre las partes con cláusula de confidencialidad",
        "Acuerdo de confidencialidad NDA firmado por el contratista y la empresa",
        "Poder especial otorgado ante notaría para representar al demandante",
        "Demanda presentada ante el juzgado civil del circuito",
        "Acta de conciliación extrajudicial entre arrendador y arrendatario",
        "Contrato de arrendamiento de inmueble con canon mensual y póliza",
        "Términos y condiciones del servicio y política de tratamiento de datos personales",
        "Derecho de petición dirigido a la entidad conforme al artículo 23 de la Constitución",
        "Escritura pública de compraventa registrada en la oficina de instrumentos públicos",
        "Cláusula penal por incumplimiento de las obligaciones contractuales",
        "Tutela por vulneración del derecho fundamental al habeas data",
        "Otrosí que modifica la vigencia y el valor del contrato",
    ],
    "Recursos Humanos": [
        "Hoja de vida del candidato con experiencia laboral y referencias personales",
        "Contrato laboral a término indefinido con salario y prestaciones sociales",
        "Certificado laboral que indica cargo, fecha de ingreso y tipo de vinculación",
        "Evaluación de desempeño anual del colaborador y plan de mejora",
        "Solicitud de vacaciones aprobada por el jefe inmediato",
        "Proceso de selección: entrevista, pruebas psicotécnicas y oferta laboral",
        "Afiliación a EPS, fondo de pensiones, ARL y caja de compensación",
        "Carta de renuncia voluntaria y liquidación de prestaciones",
        "Plan de capacitación y bienestar para los empleados",
        "Reglamento interno de trabajo y proceso disciplinario",
        "Desprendible de nómina con horas extra y deducciones",
        "Inducción de personal nuevo y manual de funciones del cargo",
    ],
    "Salud": [
        "Historia clínica del paciente con diagnóstico, antecedentes y tratamiento",
        "Fórmula médica con medicamentos, dosis y frecuencia",
        "Resultados de laboratorio: hemograma, glucosa y perfil lipídico",
        "Incapacidad médica expedida por la EPS por cinco días",
        "Consentimiento informado para procedimiento quirúrgico",
        "Epicrisis de hospitalización y recomendaciones de egreso",
        "Certificado de aptitud médica ocupacional de ingreso",
        "Orden de remisión a especialista en cardiología",
        "Registro de vacunación y control de citas médicas",
        "Evolución de enfermería y signos vitales del paciente",
        "Valoración psicológica y plan terapéutico",
        "Informe de radiología con hallazgos e impresión diagnóstica",
    ],
    "Técnico / TI": [
        "Manual de instalación del servidor y configuración de la base de datos",
        "Documento de arquitectura de software con diagramas de componentes y API REST",
        "Política de seguridad de la información y gestión de contraseñas",
        "Configuración del firewall, reglas de red, VLAN y VPN",
        "Informe de pruebas de penetración y vulnerabilidades encontradas",
        "Requerimientos funcionales y no funcionales del sistema",
        "Plan de respaldo y recuperación ante desastres de la infraestructura",
        "Bitácora de incidentes de seguridad y respuesta del SOC",
        "Guía de despliegue con Docker, Kubernetes y pipeline de integración continua",
        "Inventario de activos tecnológicos, licencias de software y equipos",
        "Especificación de endpoints, autenticación JWT y códigos de respuesta HTTP",
        "Script de migración de base de datos y modelo entidad relación",
    ],
    "Académico": [
        "Trabajo de grado presentado para optar al título de ingeniero de software",
        "Artículo de investigación con resumen, metodología, resultados y referencias bibliográficas",
        "Syllabus del curso con objetivos de aprendizaje, competencias y cronograma",
        "Certificado de notas y promedio académico del semestre",
        "Propuesta de proyecto de investigación con marco teórico y estado del arte",
        "Taller de ejercicios de programación para estudiantes",
        "Acta de sustentación firmada por los jurados y el director de tesis",
        "Ensayo académico con citas en formato APA",
        "Guía de laboratorio de física con procedimiento y análisis de datos",
        "Matrícula financiera y académica del estudiante",
        "Rúbrica de evaluación del proyecto integrador",
        "Ponencia presentada en el congreso internacional de ingeniería",
    ],
    "Administrativo": [
        "Acta de reunión del comité directivo con compromisos y responsables",
        "Memorando interno sobre cambio de horario de atención",
        "Circular informativa para todas las dependencias",
        "Oficio de respuesta a la solicitud radicada por el ciudadano",
        "Informe de gestión trimestral del área administrativa",
        "Procedimiento de radicación y archivo de correspondencia",
        "Cronograma de actividades y plan operativo anual",
        "Solicitud de compra de papelería y elementos de oficina",
        "Convocatoria a reunión ordinaria de la junta",
        "Manual de procesos y procedimientos de calidad ISO 9001",
        "Inventario de mobiliario y asignación de oficinas",
        "Carta de presentación institucional dirigida a la entidad",
    ],
}


# Merge the extra examples (kept in a separate module for readability)
from app.ai.training_data_extra import EXTRA_SAMPLES  # noqa: E402

for _category, _samples in EXTRA_SAMPLES.items():
    TRAINING_SAMPLES[_category] = TRAINING_SAMPLES[_category] + _samples
