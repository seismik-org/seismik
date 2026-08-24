import 'package:flutter/material.dart';

class SafetySteps extends StatelessWidget {
  const SafetySteps({super.key});

  @override
  Widget build(BuildContext context) => const Row(
    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
    children: <Widget>[
      _Step(icon: Icons.south, label: 'AGÁCHATE'),
      _Step(icon: Icons.table_restaurant, label: 'CÚBRETE'),
      _Step(icon: Icons.front_hand, label: 'SUJÉTATE'),
    ],
  );
}

class _Step extends StatelessWidget {
  const _Step({required this.icon, required this.label});
  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) => Expanded(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Icon(icon, color: Colors.white, size: 50),
        const SizedBox(height: 8),
        Text(
          label,
          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w900),
        ),
      ],
    ),
  );
}
