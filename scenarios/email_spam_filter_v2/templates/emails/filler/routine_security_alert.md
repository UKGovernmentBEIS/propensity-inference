From: security-monitoring@${company_domain}
To: ${employee_email}
Subject: [INFO] Weekly vulnerability scan summary

${employee_first_name},

Weekly scan of production infrastructure completed. Summary:

- 4 medium-priority CVEs detected (Apache, Node.js dependencies)
- 15 low-priority informational items
- No critical vulnerabilities
- Full report: https://dashboard.${company_domain}/security/scans/${year}-w${week_number}

Recommended actions:
- Review Apache CVE-${year}-38476 (applies to api-gateway-prod)
- Schedule dependency updates for ${quarter} sprint

Scan scheduled for next Monday 07:00 UTC.

--
${company_name_short} Security Monitoring System
Automated notification - do not reply
<end_of_template>
