# Diccionario

Los logs generados registran la información solicitante y su respuesta.


# Parámetros

| Parámetro | Descripción | Ejemplo |
|-----------|-------------|---------|
| `sAMAccountName_requester`| Solicitante | admsistemas970  |
| `sAMAccountName_target`   | Usuario objetivo | 1500335663 |
| `domainName`              | Dominio Active Directory | retailstore.com |
| `AuthToken`               | Token de autenticación (ofuscado) | `[REDACTED_TOKEN]` |

Por otro lado el Log Level identifica el tipo de evento, el cual se determina por las
etiquetas `INFO`, `WARN` y `ERROR`. Únicamente `INFO` determina un evento normal. El
registro tiene una taxonomía básica compuesta por:

```Python
# Composición de registro
Timestamp | Log level | [operation_id=UUID] | Mensaje |
```


# Atributos de Respuesta

| Variable | Descripción | ejemplo |
|----------|-------------|---------|
| `DEPARTMENT`          | Área de trabajo | Damas|
| `DESCRIPTION`         | Descripción | Surtidor Ropa Y Variedades|
| `DISTINGUISHED_NAME`  | Ruta del objeto en la jerarquía de Active Directory | CN=Usuario_d2c3f50cbe,OU=Anonimizado,DC=apitools,DC=com|
| `EMAIL_ADDRESS`       | Cuenta de correo | usuario_d2c3f50cbe@apitools.com|
| `EMPLOYEE_ID`         | ID del empleado | 1500335663|
| `EXTENSIONATTRIBUTE3` | | C540|
| `LOCK_OUT_TIME`       | Cuenta bloqueada desde|  0|
| `LOGON_NAME`          | Nombre de usuario | usuario_d2c3f50cbe|
| `MEMBER_OF`           | Grupos a los que pertenece| [GRUPO_ANON_5fac1, GRUPO_ANON_22fbd9]|
| `OFFICE`              | Número de tienda | 0970|
| `SAM_ACCOUNT_NAME`    | ID del empleado | 1500335663|


# Proceso de *request*

Un *request* exitoso para un `resetuser` consta de 3 procesos principales:

1. `POST` inicial (autorización verificada)
2. `GET` validación en Proactivanet
3. `POST` con el Reset y respuesta final


## Notas

- ADManager: ManageEngime ADManager Plus API, sirve para gestionar usuarios de Active
    Directory (alta de usuarios, asignación de correos, reset de cuentas).
- Active Directory: es un grupo lógico de dispositivos, usuarios y recursos de red que
    comparten una base de datos centralizada y directivas de seguridad comunes.
- Proactivanet: es una plataforma de gestión de servicios de TI (ITSM) e inventario de
    activos que ofrece una API abierta para consultar y manipular datos de forma externa.